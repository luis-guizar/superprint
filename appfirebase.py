# Import required libraries
from flask import Flask, request, send_file, jsonify  # Web framework components
import pdfkit  # HTML to PDF conversion library
import qrcode  # QR code generation library
from io import BytesIO  # In-memory byte stream handling
import base64  # Base64 encoding/decoding
import os  # File system operations
from PyPDF2 import PdfMerger  # PDF merging functionality
from jinja2 import Environment, BaseLoader  # Template engine components
import firebase_admin  # Firebase administration SDK
from firebase_admin import credentials, storage, firestore  # Firebase services
import datetime  # Date/time operations
import hashlib  # Hash generation for cache validation

# Initialize Flask application instance
app = Flask(__name__)

# Firebase Configuration ========================================================
# Load Firebase service account credentials from JSON file
cred = credentials.Certificate("path/to/serviceAccountKey.json")

# Initialize Firebase Admin SDK with project configuration
firebase_admin.initialize_app(cred, {
    'storageBucket': 'your-project-id.appspot.com',  # Cloud Storage bucket name
    'projectId': 'your-project-id'  # Firebase project ID
})

# Application Configuration =====================================================
WKHTMLTOPDF_PATH = "/usr/bin/wkhtmltopdf"  # Path to wkhtmltopdf executable
config = pdfkit.configuration(wkhtmltopdf=WKHTMLTOPDF_PATH)  # PDFKit configuration

# Template Caching System =======================================================
template_cache = {}  # In-memory cache for storing templates
CACHE_TTL = 300  # Cache time-to-live in seconds (5 minutes)

def generate_qr_code(data):
    """
    Generates a QR code image from provided data and returns it as base64 string
    Args:
        data: String content to encode in QR code
    Returns:
        Base64 encoded PNG image as string
    """
    # Configure QR code parameters
    qr = qrcode.QRCode(
        version=1,  # Size version (1-40, 1=21x21 modules)
        error_correction=qrcode.constants.ERROR_CORRECT_L,  # Error correction level (7%)
        box_size=10,  # Pixels per QR code module
        border=4,  # White border width in modules
    )
    
    # Add data to QR code and generate
    qr.add_data(data)
    qr.make(fit=True)  # Automatically adjust size
    
    # Create image with specified colors
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Save image to in-memory buffer
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    
    # Convert to base64 string for HTML embedding
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

class FirebaseLoader(BaseLoader):
    """
    Custom Jinja2 template loader for Firebase Cloud Storage
    Inherits from BaseLoader to implement custom loading logic
    """
    
    def get_source(self, environment, template_path):
        """
        Main method to load template source code
        Args:
            environment: Jinja2 environment
            template_path: Relative template path
        Returns:
            tuple: (source, template_path, uptodate callback)
        """
        # Check cache first for existing valid template
        cached = self._check_cache(template_path)
        if cached:
            # Return cached content with dummy uptodate checker
            return cached, template_path, lambda: True
            
        # Cache miss - fetch from Firebase Storage
        bucket = storage.bucket()  # Get storage bucket instance
        blob = bucket.blob(f"templates/{template_path}")  # Create blob reference
        template_content = blob.download_as_text()  # Download template content
        
        # Update cache with new template version
        self._update_cache(template_path, template_content)
        
        # Return content with path and uptodate checker
        return template_content, template_path, lambda: False

    def _check_cache(self, template_path):
        """
        Checks if template exists in cache and is still valid
        Args:
            template_path: Template identifier
        Returns:
            str|None: Cached content if valid, otherwise None
        """
        now = datetime.datetime.now().timestamp()  # Current timestamp
        
        if template_path in template_cache:
            entry = template_cache[template_path]
            # Check if cache entry is still within TTL
            if now - entry['timestamp'] < CACHE_TTL:
                return entry['content']
        return None

    def _update_cache(self, template_path, content):
        """
        Updates cache with new template content
        Args:
            template_path: Template identifier
            content: Template content to cache
        """
        template_cache[template_path] = {
            'content': content,  # Actual template content
            'timestamp': datetime.datetime.now().timestamp(),  # Cache time
            'hash': hashlib.md5(content.encode()).hexdigest()  # Content hash
        }

# Jinja2 Environment Setup ======================================================
# Create Jinja2 environment with custom Firebase loader
env = Environment(loader=FirebaseLoader())

def qr_filter(data, style=None):
    """
    Jinja2 filter for generating QR code images
    Usage in templates: {{ value|render_qrcode(style='...') }}
    Args:
        data: Data to encode in QR code
        style: Optional CSS style string
    Returns:
        str: HTML img tag with embedded QR code
    """
    img_base64 = generate_qr_code(data)  # Generate QR code
    style_attr = f'style="{style}"' if style else ''  # Handle optional styling
    return f'<img src="data:image/png;base64,{img_base64}" {style_attr}>'

# Register custom filter with Jinja environment
env.filters['render_qrcode'] = qr_filter

# PDF Generation Endpoint =======================================================
@app.route("/generate_pdf", methods=["POST"])
def generate_pdf():
    """
    Main endpoint for PDF generation
    Handles POST requests with JSON payload containing template requests
    """
    try:
        # Validate request format
        requests_data = request.json
        if not isinstance(requests_data, list):
            return jsonify({"error": "Expected array of template requests"}), 400

        # Initialize PDF merger for combining multiple PDFs
        merger = PdfMerger()
        
        # Process each template request in the array
        for req in requests_data:
            # Extract template name and data with defaults
            template_name = req.get("template")
            data = req.get("data", {})  # Empty dict if no data provided

            # Validate required template name
            if not template_name:
                return jsonify({"error": "Missing template name"}), 400

            try:
                # Get template from Firebase via Jinja loader
                template = env.get_template(template_name)
                
                # Render template with provided data
                rendered_html = template.render(**data)
                
                # Convert HTML to PDF using pdfkit
                # False parameter returns PDF as bytes instead of saving to file
                pdf_bytes = pdfkit.from_string(rendered_html, False, configuration=config)
                
                # Add PDF to merger using in-memory buffer
                merger.append(BytesIO(pdf_bytes))
                
            except Exception as e:
                # Handle template-specific errors
                return jsonify({"error": f"Template processing failed: {str(e)}"}), 400

        # Finalize merged PDF
        merged_pdf = BytesIO()  # Create in-memory buffer
        merger.write(merged_pdf)  # Write merged content to buffer
        merger.close()  # Free merger resources
        merged_pdf.seek(0)  # Reset buffer position to beginning

        # Return PDF as downloadable file
        return send_file(
            merged_pdf,
            as_attachment=True,  # Force browser download dialog
            download_name="merged.pdf",  # Default filename suggestion
            mimetype="application/pdf"  # Proper MIME type header
        )

    except Exception as e:
        # Catch-all error handler
        return jsonify({"error": str(e)}), 500  # Return 500 status code

# Main Execution ================================================================
if __name__ == "__main__":
    # Start Flask development server
    app.run(host="0.0.0.0",  # Listen on all network interfaces
            port=5000)       # Use port 5000