# Import required libraries
from flask import Flask, request, send_file, jsonify  # Web framework components
import pdfkit  # HTML to PDF conversion
import qrcode  # QR code generation
from io import BytesIO  # In-memory binary streams
import base64  # Base64 encoding/decoding
import os  # File system operations
from PyPDF2 import PdfMerger  # PDF merging functionality
from jinja2 import Environment, BaseLoader  # Templating engine components

# Initialize Flask application
app = Flask(__name__)

# Configuration constants
WKHTMLTOPDF_PATH = "/usr/bin/wkhtmltopdf"  # Path to wkhtmltopdf executable
config = pdfkit.configuration(wkhtmltopdf=WKHTMLTOPDF_PATH)  # PDFKit configuration
TEMPLATES_DIR = "templates"  # Directory where HTML templates are stored

def generate_qr_code(data):
    """
    Generates a QR code image from provided data
    Args:
        data: String content to encode in QR code
    Returns:
        Base64 encoded PNG image as string
    """
    # Create QR code configuration
    qr = qrcode.QRCode(
        version=1,  # Controls size (1-40, 1=21x21 modules)
        error_correction=qrcode.constants.ERROR_CORRECT_L,  # Error correction level (L:7%)
        box_size=10,  # Number of pixels per QR code module
        border=4,  # White border around QR code (in modules)
    )
    qr.add_data(data)  # Add data to be encoded
    qr.make(fit=True)  # Automatically determine size
    
    # Create image with specific colors
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Save image to in-memory buffer
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    
    # Convert to base64 string for HTML embedding
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

def setup_jinja_environment():
    """
    Configures Jinja2 templating environment with custom filters
    Returns:
        Configured Jinja2 environment
    """
    # Create environment with string-based loader (no file system access)
    env = Environment(loader=BaseLoader())
    
    # Custom filter for QR code generation
    def qr_filter(data, style=None):
        """
        Jinja filter to generate QR code images
        Usage: {{ codigoqr | render_qrcode(style='...') }}
        """
        img_base64 = generate_qr_code(data)  # Generate QR code
        style_attr = f'style="{style}"' if style else ''  # Handle optional style
        return f'<img src="data:image/png;base64,{img_base64}" {style_attr}>'
    
    # Register custom filter with Jinja environment
    env.filters['render_qrcode'] = qr_filter
    
    return env

# Initialize Jinja environment once at startup
JINJA_ENV = setup_jinja_environment()

def render_template(template_content, data):
    """
    Renders HTML template with provided data using Jinja2
    Args:
        template_content: Raw HTML template as string
        data: Dictionary of template variables
    Returns:
        Rendered HTML content
    """
    # Create template from string and render with data
    template = JINJA_ENV.from_string(template_content)
    return template.render(**data)

@app.route("/generate_pdf", methods=["POST"])
def generate_pdf():
    """
    Main endpoint for PDF generation
    Handles POST requests with JSON payload
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
            # Extract request parameters with defaults
            template_name = req.get("template")
            data = req.get("data", {})  # Default to empty dict
            
            # Validate required template name
            if not template_name:
                return jsonify({"error": "Missing template name"}), 400

            # Build full template path and verify existence
            template_path = os.path.join(TEMPLATES_DIR, template_name)
            if not os.path.exists(template_path):
                return jsonify({"error": f"Template {template_name} not found"}), 404

            # Read template file contents
            with open(template_path, "r", encoding="utf-8") as f:
                template_content = f.read()

            # Render template with data using Jinja2
            rendered_html = render_template(template_content, data)

            # Convert rendered HTML to PDF
            # Note: False argument means return as bytes instead of saving to file
            pdf_bytes = pdfkit.from_string(rendered_html, False, configuration=config)
            
            # Add PDF to merger using in-memory buffer
            merger.append(BytesIO(pdf_bytes))

        # Finalize merged PDF
        merged_pdf = BytesIO()  # Create in-memory buffer
        merger.write(merged_pdf)  # Write merged content to buffer
        merger.close()  # Free resources
        merged_pdf.seek(0)  # Reset buffer position to start

        # Return merged PDF as downloadable file
        return send_file(
            merged_pdf,
            as_attachment=True,  # Force download dialog
            download_name="merged.pdf",  # Default filename
            mimetype="application/pdf"  # MIME type header
        )

    except Exception as e:
        # Handle any unexpected errors
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # Start Flask development server
    app.run(host="0.0.0.0",  # Listen on all network interfaces
            port=5000)       # Use port 5000 