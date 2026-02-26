
🎤 Voice Interview App
A full-stack Flask web application for asynchronous voice-based interview capture.
Candidates record audio responses to predefined interview questions, and admins can review and replay submissions.
⚠️ This system is for interview capture only. Evaluation, scoring, and hiring decisions are intentionally out of scope.

![Python](https://img.shields.io/badge/Python-3.8+-blue?style=flat-square)
![Flask](https://img.shields.io/badge/Flask-3.0.3-green?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)

---

## ✨ Features

### 👥 Candidate Features
- ✅ **Easy Registration** - Enter name and email
- ✅ **Browser-Based Recording** - Record audio directly in the browser (no external apps needed)
- ✅ **Multiple Questions** - Answer unlimited interview questions
- ✅ **Instant Playback** - Listen to recordings before submitting
- ✅ **One-Click Submission** - Submit all answers at once
- ✅ **Responsive Design** - Works on desktop, tablet, and mobile

### 🔧 Admin Features
- ✅ **Secure Login** - Admin authentication with password hashing
- ✅ **Question Management** - Add, edit, and delete interview questions
- ✅ **Dashboard** - View statistics (candidates, questions, submissions)
- ✅ **Audio Review** - Play candidate responses directly in the dashboard
- ✅ **Review Dashboard** - Replay candidate audio submissions
- ✅ **Submission History** - View all candidates and their submissions

### 🔐 Security
- Password hashing with Werkzeug
- Session-based authentication
- Secure file uploads
- SQL injection protection (SQLAlchemy ORM)
- CSRF protection (Flask)

---

### 🚫 Explicitly Out of Scope
- ❌ Voice evaluation or scoring
- ❌ Candidate ranking or shortlisting
- ❌ Sentiment or emotion analysis
- ❌ Hiring or selection decisions

## 📋 Project Structure

```
voice-interview-app/
├── main.py                         # Main Flask application
├── streamlit_app.py                 # Streamlit entrypoint (recommended)
├── requirements.txt                # Python dependencies
├── interview.db                    # SQLite database (auto-created)
├── .env.example                    # Environment variables template
├── firebase.json                   # Firebase configuration
├── README.md                       # This file
│
├── uploads/                        # Audio file storage (auto-created)
│
├── templates/                      # HTML templates
│   ├── base.html                   # Base template
│   ├── index.html                  # Homepage
│   ├── interview.html              # Interview page (candidates)
│   ├── thankyou.html               # Thank you page
│   ├── 404.html                    # 404 error page
│   ├── 500.html                    # 500 error page
│   └── admin/
│       ├── login.html              # Admin login
│       ├── dashboard.html          # Admin dashboard
│       ├── questions.html          # Manage questions
│       ├── submissions.html        # View submissions
│       └── submission_detail.html  # Review submission
│
└── static/                         # Static files
    ├── style.css                   # CSS styles
    └── recorder.js                 # Audio recording JavaScript
```

---

## 🚀 Quick Start (Local Development)

### Prerequisites
- Python 3.8+
- pip (Python package manager)
- Modern web browser (Chrome, Firefox, Safari, Edge)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Nikhil1081/voice-interview-app.git
   cd voice-interview-app
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   
   # Activate virtual environment
   # On Windows:
   venv\Scripts\activate
   
   # On macOS/Linux:
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Create .env file:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and change the `SECRET_KEY` to a secure random string:
   ```bash
   python -c "import os; print(os.urandom(24).hex())"
   ```

5. **Run the application:**
   ```bash
   python main.py
   ```

   **Or run the Streamlit version (recommended):**
   ```bash
   streamlit run streamlit_app.py
   ```

6. **Access the app:**
   **If running Flask (`python main.py`):**
   - **Candidate:** http://127.0.0.1:5000/
   - **Admin:** http://127.0.0.1:5000/admin/login

   **If running Streamlit (`streamlit run streamlit_app.py`):**
   - Open: http://localhost:8501
   - Use the sidebar to switch between **Candidate** and **Admin**
   - **Default Admin Credentials:**
     - Username: `admin`
     - Password: `admin123`
     - ⚠️ **CHANGE THESE IMMEDIATELY IN PRODUCTION!**

---

## 🌍 Deployment

### Option 1: Deploy to Railway

#### Prerequisites
- Railway Account (railway.app)
- GitHub repository

#### Steps:

1. **Push to GitHub** (already done!)

2. **Connect to Railway:**
   - Go to [railway.app](https://railway.app)
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Select this repository
   - Click "Deploy"

3. **Set Environment Variables:**
   - Go to "Variables" tab
   - Add:
     - `SECRET_KEY=your-secret-key`
     - `ADMIN_USERNAME=admin`
     - `ADMIN_PASSWORD=secure-password`
     - `FLASK_ENV=production`

4. **Your app will be live automatically!**

---

### Option 2: Deploy to Firebase Hosting + Cloud Functions (Recommended)

#### Prerequisites
- [Firebase CLI](https://firebase.google.com/docs/cli) installed
- [Google Cloud Account](https://cloud.google.com)
- Node.js 14+ (for Firebase CLI)

#### Steps:

1. **Initialize Firebase:**
   ```bash
   npm install -g firebase-tools
   firebase login
   firebase init
   ```
   Select:
   - ✅ Hosting
   - ✅ Functions
   - Select your Firebase project

2. **Create Cloud Functions wrapper:**
   Create `functions/main.py`:
   ```python
   import functions_framework
   import sys
   sys.path.append('..')
   from app import app

   @functions_framework.http
   def interview_app(request):
       with app.test_request_context(
           request.path,
           method=request.method,
           data=request.get_data(),
           headers=dict(request.headers)
       ):
           return app.full_dispatch_request()
   ```

3. **Create `functions/requirements.txt`:**
   ```
   Flask==3.0.3
   Flask-SQLAlchemy==3.1.1
   Werkzeug==3.0.3
   python-dotenv==1.0.0
   ```

4. **Deploy:**
   ```bash
   firebase deploy
   ```

5. **Your app will be live at:** `https://your-project.firebaseapp.com`

---

### Option 3: Deploy to Heroku

#### Prerequisites
- [Heroku CLI](https://devcenter.heroku.com/articles/heroku-cli)
- Heroku Account

#### Steps:

1. **Create `Procfile` in root directory:**
   ```
   web: gunicorn app:app
   ```

2. **Update `requirements.txt`:**
   ```bash
   pip freeze > requirements.txt
   ```

3. **Initialize Git (if not already):**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   ```

4. **Create Heroku app and deploy:**
   ```bash
   heroku login
   heroku create your-app-name
   
   # Set environment variables
   heroku config:set SECRET_KEY="your-secret-key"
   heroku config:set ADMIN_USERNAME="your-admin-username"
   heroku config:set ADMIN_PASSWORD="your-secure-password"
   
   git push heroku main
   ```

5. **Your app will be live at:** `https://your-app-name.herokuapp.com`


### Option 3: Deploy to Streamlit Community Cloud (Recommended)

#### Prerequisites
- GitHub repository
- Streamlit Community Cloud account

#### Steps

1. **Push to GitHub**

2. **Create a Streamlit app**
   - Go to https://share.streamlit.io
   - Click "New app"
   - Select your repo and branch
   - Set **Main file path** to:
     - `streamlit_app.py`

3. **Configure secrets (recommended)**
   In the Streamlit app settings, add secrets:
   - `SECRET_KEY = "<random>"`
   - `ADMIN_USERNAME = "admin"`
   - `ADMIN_PASSWORD = "<strong password>"`
   - (Optional) `DATABASE_URL = "sqlite:///interview.db"`

4. **Deploy**
   Streamlit will install from `requirements.txt` and launch automatically.

   Note: the default setup uses local SQLite (`interview.db`) and stores audio in `uploads/`. On Streamlit Community Cloud, local disk is not a durable database; for long-term persistence, configure an external DB + file storage.

---

### Option 4: Deploy to PythonAnywhere

1. **Sign up at [pythonanywhere.com](https://pythonanywhere.com)**

2. **Upload your code via Git:**
   ```bash
   git clone https://github.com/Nikhil1081/voice-interview-app.git
   ```

3. **Create virtual environment and install requirements**

4. **Configure Web App:**
   - Create a new web app
   - Select Flask and Python 3.10+
   - Point to your `main.py`
   - Configure WSGI file

5. **Set environment variables in Web tab**

---

## 📚 API Endpoints

### Candidate Routes
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/` | Homepage |
| GET/POST | `/interview` | Interview page - record answers |
| GET | `/uploads/<filename>` | Serve audio files |

### Admin Routes
| Method | Route | Description |
|--------|-------|-------------|
| GET/POST | `/admin/login` | Admin login |
| GET | `/admin/logout` | Admin logout |
| GET | `/admin` | Admin dashboard |
| GET/POST | `/admin/questions` | Manage questions |
| POST | `/admin/questions/<id>/edit` | Edit question |
| POST | `/admin/questions/<id>/delete` | Delete question |
| GET | `/admin/submissions` | View submissions |
| GET/POST | `/admin/submissions/<id>` | Review submission (audio playback & notes) |
| POST | `/admin/submissions/<id>/delete` | Delete submission |

---

## 🗄️ Database Schema

### Admin
```
id (Integer) - Primary Key
username (String) - Unique
password_hash (String)
```

### Question
```
id (Integer) - Primary Key
text (Text) - Question text
created_at (DateTime)
```

### Candidate
```
id (Integer) - Primary Key
name (String)
email (String) - Unique
created_at (DateTime)
```

### Submission
```
id (Integer) - Primary Key
candidate_id (Foreign Key) -> Candidate
question_id (Foreign Key) -> Question
audio_filename (String)
transcript (Text) - Optional
feedback (Text) - Optional admin remarks (non-evaluative)
created_at (DateTime)
```

---

## 🔧 Configuration

### Environment Variables

Create a `.env` file (copy from `.env.example`):

```bash
# Flask
FLASK_ENV=production
FLASK_DEBUG=False
SECRET_KEY=your-secret-key-here

# Database
DATABASE_URL=sqlite:///interview.db

# Admin
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123

# Server
HOST=0.0.0.0
PORT=5000
```

### Generate Secure Secret Key

```python
import os
print(os.urandom(24).hex())
```

---

## 🧪 Testing

### Manual Testing Checklist

**Candidate Flow:**
- [ ] Navigate to homepage
- [ ] Start interview
- [ ] Enter name and email
- [ ] Record answer to question 1
- [ ] Listen to playback
- [ ] Record answer to question 2
- [ ] Submit interview
- [ ] See success message

**Admin Flow:**
- [ ] Login with admin credentials
- [ ] View dashboard statistics
- [ ] Add new question
- [ ] Edit existing question
- [ ] View all submissions
- [ ] Play candidate audio
- [ ] Give feedback
- [ ] Save feedback

---

## 🐛 Troubleshooting

### Microphone Access Denied
- **Browser:** Chrome, Firefox, Safari, Edge all support getUserMedia
- **Solution:** Allow microphone access when browser asks
- **Secure Context:** App must be HTTPS in production (not needed for localhost)

### Audio File Not Saving
- Check `uploads/` folder has write permissions
- Verify file size is under 50MB
- Check browser console for errors

### Database Issues
- Delete `interview.db` to reset
- App will recreate it on next run
- Reset admin credentials: edit `main.py` to change defaults

### Port Already in Use
```bash
# Find process using port 5000
lsof -i :5000

# Kill process
kill -9 <PID>

# Or use different port
python main.py --port 5001
```

---

## 📈 Future Enhancements

> (Phase-2 / Future Work — NOT part of this hackathon)

- Audio transcription (Google Speech-to-Text API)
- Candidate scoring system
- AI-powered evaluation (post-interview analysis)
- Email notifications
- Export reports (PDF/Excel)
- Video recording support
- Question templates library
- Multi-language support
- Advanced analytics dashboard

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs and feature requests.

---

## 📝 License

This project is licensed under the MIT License - see LICENSE file for details.

---

## 📞 Support

If you have any questions or run into issues:

1. Check [Troubleshooting](#-troubleshooting) section
2. Review GitHub Issues
3. Create a new issue with:
   - Error message
   - Steps to reproduce
   - Your environment (OS, Python version, browser)

---

## 👨‍💻 Author

**Nikhil Vankala**
- GitHub: [@Nikhil1081](https://github.com/Nikhil1081)
- Location: Bengaluru, India

---

## 🙏 Acknowledgments

- Flask documentation and community
- MediaRecorder API for browser audio
- SQLAlchemy ORM
- Firebase for hosting

---

**⭐ If you find this project helpful, please give it a star! ⭐**
