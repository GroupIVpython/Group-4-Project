from flask import Flask, render_template, request, jsonify
import logging
from seleniumForm2 import run_selenium_with_input  # Import from seleniumForm2.py

# Flask Setup
app = Flask(__name__)

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

# Routes
@app.route('/')
def index():
    return render_template('Form.html')  # Serve Form.htlm

@app.route('/fill-form', methods=['POST'])
def fill_form():
    try:
        # Geting user input from form (sent as JSON from Form.html)
        user_data = request.get_json()
        
        # Validate input
        required_fields = ['fullName', 'email', 'company', 'projectTitle']
        for field in required_fields:
            if not user_data.get(field):
                return jsonify({
                    'success': False,
                    'message': f'{field.replace("fullName", "Full Name").replace("projectTitle", "Project Title").title()} is required.'
                }), 400

        # Log received data
        logging.info(f"Received user data: {user_data}")

        # Run Selenium automation with user data
        success, message = run_selenium_with_input(user_data)
        
        return jsonify({
            'success': success,
            'message': message
        })
    except Exception as e:
        logging.error(f"Error processing form submission: {e}")
        return jsonify({
            'success': False,
            'message': f"Server error: {str(e)}"
        }), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
