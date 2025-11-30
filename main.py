import os
import time
import re
import json
import fitz  # PyMuPDF
from PIL import Image
import google.generativeai as genai
from flask import Flask, render_template, request, jsonify, url_for
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['EXTRACTED_FOLDER'] = 'static/extracted'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# Configure Gemini with REST transport
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"), transport="rest")

# Ensure directories exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['EXTRACTED_FOLDER'], exist_ok=True)

# Global variables
CHAT_SESSION = None
CURRENT_PDF_PATH = None
VISION_MODEL_NAME = 'gemini-2.5-flash'
VISION_MODEL = genai.GenerativeModel(VISION_MODEL_NAME)

def upload_to_gemini(path, mime_type=None):
    file = genai.upload_file(path, mime_type=mime_type)
    return file

def wait_for_files_active(files):
    print("Waiting for file processing...")
    for name in (file.name for file in files):
        file = genai.get_file(name)
        while file.state.name == "PROCESSING":
            time.sleep(2)
            file = genai.get_file(name)
        if file.state.name != "ACTIVE":
            raise Exception(f"File {file.name} failed to process")

def extract_page_image(pdf_path, page_num):
    try:
        doc = fitz.open(pdf_path)
        if page_num < 1 or page_num > len(doc): return None, None
        page = doc.load_page(page_num - 1) 
        pix = page.get_pixmap(matrix=fitz.Matrix(3, 3)) 
        image_filename = f"page_{page_num}_{int(time.time())}.png"
        image_path = os.path.join(app.config['EXTRACTED_FOLDER'], image_filename)
        pix.save(image_path)
        doc.close()
        return image_filename, image_path
    except Exception as e:
        print(f"Error extracting image: {e}")
        return None, None

def get_diagram_bounding_box(image_path):
    try:
        img_file = upload_to_gemini(image_path, mime_type="image/png")
        wait_for_files_active([img_file])
        prompt = """
        Analyze this image page. Your task is to find the main diagram, flowchart, or chart.
        Goal: Provide a tight bounding box around ONLY the graphical elements.
        CRITICAL: Exclude any surrounding paragraph text, headers, footers, or page numbers.
        Return the coordinates strictly as a JSON list of normalized integers (0-1000 scale): [ymin, xmin, ymax, xmax].
        If no clear diagram, return [].
        """
        response = VISION_MODEL.generate_content([img_file, prompt])
        clean_json = response.text.replace('```json', '').replace('```', '').strip()
        box = json.loads(clean_json)
        return box if box and len(box) == 4 else None
    except Exception as e:
        print(f"Failed to find bounding box: {e}")
        return None

def crop_image_to_box(image_path, box, padding=30):
    try:
        img = Image.open(image_path)
        width, height = img.size
        ymin, xmin, ymax, xmax = box
        top = max(0, (ymin / 1000) * height - padding)
        left = max(0, (xmin / 1000) * width - padding)
        bottom = min(height, (ymax / 1000) * height + padding)
        right = min(width, (xmax / 1000) * width + padding)
        cropped_img = img.crop((left, top, right, bottom))
        cropped_img.save(image_path)
        return True
    except Exception as e:
        print(f"Error cropping image: {e}")
        return False

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    global CHAT_SESSION, CURRENT_PDF_PATH
    if 'file' not in request.files: return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({'error': 'No selected file'}), 400

    if file:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        CURRENT_PDF_PATH = filepath
        mime_type = 'application/pdf'
        if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
             mime_type = 'image/jpeg' if not filename.lower().endswith('.png') else 'image/png'

        try:
            gemini_file = upload_to_gemini(filepath, mime_type=mime_type)
            wait_for_files_active([gemini_file])
            
            system_prompt = "You are an expert tutor. Answer based strictly on the provided file. If you mention a diagram, end with [[PAGE_REF: page_number]]."
            
            model = genai.GenerativeModel(model_name=VISION_MODEL_NAME, system_instruction=system_prompt)
            CHAT_SESSION = model.start_chat(history=[
                {"role": "user", "parts": [gemini_file, "Analyze this document."]},
                {"role": "model", "parts": ["Ready."]}
            ])
            return jsonify({'message': 'File processed', 'filename': filename})
        except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/ask', methods=['POST'])
def ask_question():
    global CHAT_SESSION, CURRENT_PDF_PATH
    if CHAT_SESSION is None: return jsonify({'error': 'Please upload a file first.'}), 400
    
    data = request.json
    question = data.get('question'); length = data.get('length', 'medium')
    
    extra_instruction = ""
    if any(word in question.lower() for word in ["diagram", "image", "figure", "flowchart"]):
        extra_instruction = " LOCATE any relevant diagrams and cite the Page Number using [[PAGE_REF: X]]."
    
    prompt = f"{question} (Length: {length}){extra_instruction}"

    try:
        response = CHAT_SESSION.send_message(prompt)
        answer_text = response.text
        image_url = None
        
        match = re.search(r'\[\[PAGE_REF:\s*(\d+)\]\]', answer_text)
        if match and CURRENT_PDF_PATH and CURRENT_PDF_PATH.endswith('.pdf'):
            page_num = int(match.group(1))
            extracted_filename, full_image_path = extract_page_image(CURRENT_PDF_PATH, page_num)
            if full_image_path:
                bounding_box = get_diagram_bounding_box(full_image_path)
                if bounding_box: crop_image_to_box(full_image_path, bounding_box)
                image_url = url_for('static', filename=f'extracted/{extracted_filename}')
            answer_text = answer_text.replace(match.group(0), "")

        return jsonify({'answer': answer_text, 'image': image_url})
    except Exception as e: return jsonify({'error': str(e)}), 500

# --- UPDATED QUIZ ROUTE ---
@app.route('/generate_quiz', methods=['POST'])
def generate_quiz():
    global CHAT_SESSION
    if CHAT_SESSION is None: return jsonify({'error': 'No file.'}), 400
    
    data = request.json
    count = data.get('count', 5)
    topic = data.get('topic', 'the entire document')
    difficulty = data.get('difficulty', 'Medium')
    q_type = data.get('type', 'multiple_choice') # multiple_choice, short_answer, true_false
    
    # Construct dynamic prompt
    structure_instruction = ""
    if q_type == 'multiple_choice':
        structure_instruction = '[{ "question": "...", "options": ["A", "B", "C", "D"], "answer": "Option Text" }]'
    elif q_type == 'true_false':
        structure_instruction = '[{ "question": "...", "options": ["True", "False"], "answer": "True" }]'
    else: # Short Answer or Fill in Blanks
        structure_instruction = '[{ "question": "...", "answer": "The Answer" }]'

    prompt = f"""
    Generate {count} {difficulty} questions about '{topic}' based on the document.
    Question Type: {q_type}.
    Format strictly as a JSON array. Do not use Markdown.
    Structure: {structure_instruction}
    """
    
    try:
        response = CHAT_SESSION.send_message(prompt)
        return jsonify({'quiz_data': response.text.replace('```json', '').replace('```', '').strip(), 'type': q_type})
    except Exception as e: return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # usage_reloader=False stops it from restarting when you save files or system files touch
    app.run(debug=True, port=5000, threaded=True, use_reloader=False)