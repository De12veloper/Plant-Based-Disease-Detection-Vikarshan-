from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import torch
from PIL import Image
import torchvision.transforms as transforms
import torch.nn as nn
import os
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from pymongo import MongoClient
import jwt
from functools import wraps
import datetime
import base64
from io import BytesIO
import numpy as np
from flask_mail import Mail, Message

app = Flask(__name__)
app.secret_key = 'your-secret-key'

# ✅ Mail Configuration (hardcoded for local testing only)
app.config.update(
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME='g3498217@gmail.com',
    MAIL_PASSWORD='vrrhdtxcvwltvjht',
    MAIL_DEFAULT_SENDER='g3498217@gmail.com'
)
mail = Mail(app)

# ✅ MongoDB setup
client = MongoClient("mongodb://localhost:27017/")
db = client.vikarshan
users = db.users
payments_collection = db.payments

# ✅ CNN Model
class CNNClassifier(nn.Module):
    def __init__(self, num_classes=15):
        super(CNNClassifier, self).__init__()
        self.conv_layers = nn.Sequential(
            nn.Conv2d(3, 32, 3, padding=1), nn.ReLU(), nn.BatchNorm2d(32), nn.MaxPool2d(2),
            nn.Conv2d(32, 64, 3, padding=1), nn.ReLU(), nn.BatchNorm2d(64), nn.MaxPool2d(2),
            nn.Conv2d(64, 128, 3, padding=1), nn.ReLU(), nn.BatchNorm2d(128), nn.MaxPool2d(2),
            nn.Conv2d(128, 256, 3, padding=1), nn.ReLU(), nn.BatchNorm2d(256), nn.MaxPool2d(2)
        )
        self.fc_layers = nn.Sequential(
            nn.Dropout(0.5),
            nn.Linear(256 * 8 * 8, 512), nn.ReLU(),
            nn.Dropout(0.5),
            nn.Linear(512, num_classes)
        )

    def forward(self, x):
        x = self.conv_layers(x)
        x = x.view(x.size(0), -1)
        return self.fc_layers(x)

class_names = [
    'Pepper_bell__Bacterial_spot', 'Pepper_bell__healthy', 'Potato___Early_blight',
    'Potato___Late_blight', 'Potato___healthy', 'Tomato_Bacterial_spot',
    'Tomato_Early_blight', 'Tomato_Late_blight', 'Tomato_Leaf_Mold',
    'Tomato_Septoria_leaf_spot', 'Tomato_Spider_mites_Two_spotted_spider_mite',
    'Tomato__Target_Spot', 'Tomato_Tomato_YellowLeaf_Curl_Virus',
    'Tomato__Tomato_mosaic_virus', 'Tomato_healthy'
]

model = CNNClassifier(num_classes=len(class_names))
model.load_state_dict(torch.load('final_model.pth', map_location=torch.device('cpu')))
model.eval()

transform = transforms.Compose([
    transforms.Resize((128, 128)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
])

def predict_disease(image):
    if isinstance(image, np.ndarray):
        image = Image.fromarray(image)
    image_tensor = transform(image).unsqueeze(0)
    outputs = model(image_tensor)
    probs = torch.nn.functional.softmax(outputs, dim=1)
    predicted_prob, predicted_idx = torch.max(probs, 1)
    return class_names[predicted_idx.item()], predicted_prob.item() * 100

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get('token')
        if not token:
            return redirect(url_for('auth'))
        try:
            data = jwt.decode(token, 'jwt-secret', algorithms=["HS256"])
            user = users.find_one({'email': data['email']})
            if not user:
                return redirect(url_for('auth'))
        except:
            return redirect(url_for('auth'))
        return f(*args, **kwargs)
    return decorated

@app.route('/')
@token_required
def index():
    return render_template('index.html')

@app.route('/dashboard')
@token_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/auth')
def auth():
    return render_template('auth.html')

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    if users.find_one({'email': data['email']}):
        return jsonify({'error': 'Email already registered'}), 400
    if data['password'] != data['confirmPassword']:
        return jsonify({'error': 'Passwords do not match'}), 400
    new_user = {
        'firstName': data['firstName'],
        'lastName': data['lastName'],
        'email': data['email'],
        'password': generate_password_hash(data['password']),
        'created_at': datetime.datetime.utcnow()
    }
    users.insert_one(new_user)
    token = jwt.encode({'email': new_user['email'], 'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7)}, 'jwt-secret')
    response = jsonify({'message': 'Registration successful'})
    response.set_cookie('token', token, httponly=True, secure=True, samesite='Strict')
    return response

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    user = users.find_one({'email': data['email']})
    if user and check_password_hash(user['password'], data['password']):
        token = jwt.encode({'email': user['email'], 'exp': datetime.datetime.utcnow() + datetime.timedelta(days=7)}, 'jwt-secret')
        response = jsonify({'message': 'Login successful'})
        response.set_cookie('token', token, httponly=True, secure=True, samesite='Strict')
        return response
    return jsonify({'error': 'Invalid email or password'}), 401

@app.route('/logout')
def logout():
    response = redirect(url_for('auth'))
    response.delete_cookie('token')
    return response

@app.route('/predict', methods=['POST'])
def predict():
    if 'image' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    image = Image.open(request.files['image'].stream).convert('RGB')
    predicted_class, confidence = predict_disease(image)
    return jsonify({'predicted_class': predicted_class, 'confidence': confidence})

@app.route('/api/predict-from-base64', methods=['POST'])
def predict_from_base64():
    data = request.get_json()
    image_data = data['image'].split(',')[1]
    image = Image.open(BytesIO(base64.b64decode(image_data))).convert('RGB')
    predicted_class, confidence = predict_disease(image)
    return jsonify({'predicted_class': predicted_class, 'confidence': confidence})

@app.route('/payment', methods=['GET', 'POST'])
@token_required
def payment():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        amount = request.form['amount']
        transaction_id = request.form['transaction_id']
        aadhar_file = request.files['aadhar_image']

        if aadhar_file:
            filename = secure_filename(aadhar_file.filename)
            file_data = aadhar_file.read()
            payment_doc = {
                "name": name,
                "email": email,
                "amount": amount,
                "transaction_id": transaction_id,
                "aadhar_filename": filename,
                "aadhar_file": file_data,
                "timestamp": datetime.datetime.utcnow()
            }
            payments_collection.insert_one(payment_doc)

            msg = Message("Payment Confirmation - Vikarshan", recipients=[email])
            msg.body = f"Hello {name},\n\nYour payment of ₹{amount} has been successfully received.\nTransaction ID: {transaction_id}\n\nRegards,\nVikarshan Team"
            mail.send(msg)

            flash("Payment submitted and confirmation email sent!", "success")
            return redirect('/payment')

    return render_template('payment.html')

# Optional precaution PDF download
from download.precaution_generator import download_precaution_doc
precaution_info = {
    'Pepper_bell__Bacterial_spot': 'Use copper-based fungicides, avoid overhead irrigation.',
    'Potato___Early_blight': 'Use fungicides and remove infected leaves.',
    'Potato___Late_blight': 'Apply phosphorous acid-based fungicides. Rotate crops regularly.',
    'Tomato_Late_blight': 'Remove infected plants, use resistant varieties, apply fungicides.',
}

@app.route('/download-precaution-doc')
def download_doc():
    predicted_class = request.args.get('disease', 'Potato___Early_blight')
    precaution = precaution_info.get(predicted_class, 'No specific precaution available.')
    return download_precaution_doc(predicted_class, precaution)

@app.route('/buy/earlyblight')
def buy_earlyblight():
    return redirect("https://www.flipkart.com/kay-bee-bio-pesticide-downy-raze-500ml/p/itm25d062c6db1ff")

@app.route('/buy-pesticide')
def buy_pesticide():
    return redirect("https://www.flipkart.com/search?q=early+blight+pesticide")

if __name__ == '__main__':
    app.run(debug=True)
