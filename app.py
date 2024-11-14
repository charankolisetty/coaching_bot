import os
import time
import logging
from datetime import datetime
from flask import Flask, render_template, request, session, redirect, url_for, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from config import Config
from openai import OpenAI, OpenAIError
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static')
app.config.from_object(Config)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
db = SQLAlchemy(app)

# Initialize OpenAI client
openai_client = OpenAI(api_key=app.config['OPENAI_API_KEY'])

@app.context_processor
def inject_year():
    return {'year': datetime.now().year}

# Models
class UserThread(db.Model):
    __tablename__ = 'user_threads'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False)
    thread_id = db.Column(db.String(100), unique=True, nullable=False)
    industry = db.Column(db.String(100))
    company = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
class ChatHistory(db.Model):
    __tablename__ = 'chat_history'
    id = db.Column(db.Integer, primary_key=True)
    thread_id = db.Column(db.String(100), db.ForeignKey('user_threads.thread_id'))
    username = db.Column(db.String(100), nullable=False)
    prompt = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# Create tables
with app.app_context():
    db.create_all()

# Template filters
@app.template_filter('now')
def datetime_now(format='%Y'):
    return datetime.now().strftime(format)

# Route protection decorator
def login_required(f):
    def decorated_function(*args, **kwargs):
        if not session.get('username'):
            flash('Please log in first.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        username = request.form.get("username")
        industry = request.form.get("industry")
        company = request.form.get("company")

        if not username or not industry or not company:
            flash("All fields are required", "error")
            return redirect(url_for("index"))

        try:
            # Create thread
            thread = openai_client.beta.threads.create()
            
            # Save thread info
            user_thread = UserThread(
                username=username,
                thread_id=thread.id,
                industry=industry,
                company=company
            )
            db.session.add(user_thread)
            db.session.commit()

            # Set session
            session["username"] = username
            session["industry"] = industry
            session["company"] = company
            session["thread_id"] = thread.id

            flash(f"Welcome {username}!", "success")
            return redirect(url_for("chat"))

        except Exception as e:
            logger.error(f"Error in index route: {str(e)}")
            flash("An error occurred. Please try again.", "error")
            return redirect(url_for("index"))

    return render_template("index.html")

@app.route("/chat", methods=["GET", "POST"])
@login_required
def chat():
    if request.method == "POST":
        prompt = request.form.get("prompt")
        thread_id = session.get("thread_id")

        if not prompt or not thread_id:
            return jsonify({"error": "Prompt and Thread ID are required"}), 400

        try:
            # Add message to thread
            message = openai_client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=prompt
            )

            # Run the assistant
            run = openai_client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=app.config["ASSISTANT_ID"]
            )

            max_attempts = 30  # Maximum 30 seconds wait
            attempts = 0

            # Wait for completion
            while attempts < max_attempts:
                run_status = openai_client.beta.threads.runs.retrieve(
                    thread_id=thread_id,
                    run_id=run.id
                )
                
                if run_status.status == "failed":
                    logger.error(f"Assistant run failed: {run_status.last_error}")
                    return jsonify({"error": "Assistant encountered an error"}), 500
                
                if run_status.status == "completed":
                    # Get messages
                    messages = openai_client.beta.threads.messages.list(
                        thread_id=thread_id
                    )
                    response_text = messages.data[0].content[0].text.value
                    
                    # Save to chat history
                    chat_history = ChatHistory(
                        thread_id=thread_id,
                        username=session.get('username'),
                        prompt=prompt,
                        response=response_text
                    )
                    db.session.add(chat_history)
                    db.session.commit()
                    
                    return jsonify({"response": response_text})
                
                time.sleep(1)
                attempts += 1
            
            return jsonify({"error": "Request timed out"}), 504

        except OpenAIError as e:
            logger.error(f"OpenAI error in chat route: {str(e)}")
            return jsonify({"error": "An error occurred with the AI service"}), 500
        except Exception as e:
            logger.error(f"General error in chat route: {str(e)}")
            return jsonify({"error": "An unexpected error occurred"}), 500

    # GET request - get chat history
    try:
        thread_id = session.get("thread_id")
        chat_history = ChatHistory.query.filter_by(thread_id=thread_id).order_by(ChatHistory.timestamp).all()
        return render_template("chat.html", chat_history=chat_history)
    except Exception as e:
        logger.error(f"Error retrieving chat history: {str(e)}")
        flash("Error loading chat history", "error")
        return render_template("chat.html", chat_history=[])

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out successfully.", "success")
    return redirect(url_for("index"))

@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('500.html'), 500

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))