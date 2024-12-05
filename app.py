import os
import time
import pytz
import logging
from datetime import datetime, timezone
from flask import Flask, render_template, request, session, redirect, url_for, jsonify, flash, Response
from flask_sqlalchemy import SQLAlchemy
from config import Config
from openai import OpenAI, OpenAIError
from werkzeug.middleware.proxy_fix import ProxyFix
from datetime import datetime
from functools import wraps
from dotenv import load_dotenv
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SESSION_DURATION = 20 * 60
COACHING_DURATION = 14 * 60

IST = pytz.timezone('Asia/Kolkata')
load_dotenv()

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.username != os.getenv('ADMIN_USERNAME') or auth.password != os.getenv('ADMIN_PASSWORD'):
            return Response(
                'Could not verify your access level for that URL.\n'
                'You have to login with proper credentials', 401,
                {'WWW-Authenticate': 'Basic realm="Login Required"'}
            )
        return f(*args, **kwargs)
    return decorated_function

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
    industry = db.Column(db.String(100), nullable=False)
    company = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(IST))

    # Existing relationships remain the same
    chats = db.relationship('ChatHistory', backref='thread', lazy=True,
                          cascade='all, delete-orphan')

class ChatHistory(db.Model):
    __tablename__ = 'chat_history'
    
    id = db.Column(db.Integer, primary_key=True)
    thread_id = db.Column(db.String(100), db.ForeignKey('user_threads.thread_id'))
    username = db.Column(db.String(100), nullable=False)
    prompt = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(IST))

    def __repr__(self):
        return f'<ChatHistory {self.username} - {self.timestamp}>'

# Create tables
with app.app_context():
    db.create_all()

# Template filters
@app.template_filter('format_time')
def format_time(timestamp):
    if timestamp:
        if not timestamp.tzinfo:
            timestamp = pytz.UTC.localize(timestamp)
        ist_time = timestamp.astimezone(IST)
        return ist_time.strftime('%I:%M %p')
    return ''

# Route protection decorator
def login_required(f):
    def decorated_function(*args, **kwargs):
        if not session.get('username'):
            flash('Please log in first.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@app.route("/check_sessions", methods=["POST"])
def check_sessions():
    username = request.form.get("username")
    industry = request.form.get("industry")
    company = request.form.get("company")
    
    if not all([username, industry, company]):
        return jsonify({"error": "All fields are required"}), 400
        
    try:
        # Get previous sessions for this user with same industry and company
        previous_sessions = UserThread.query.filter_by(
            username=username,
            industry=industry,
            company=company
        ).order_by(UserThread.created_at.desc()).all()
        
        return jsonify({
            "previous_sessions": [{
                "thread_id": thread.thread_id,
                "created_at": thread.created_at.astimezone(IST).strftime("%Y-%m-%d %I:%M %p"),
                "company": thread.company
            } for thread in previous_sessions]
        })
    except Exception as e:
        logger.error(f"Error checking sessions: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        username = request.form.get("username")
        industry = request.form.get("industry")
        company = request.form.get("company")
        thread_id = request.form.get("thread_id")

        session['coaching_warning_sent'] = False
        session['session_warning_sent'] = False
        session['completion_warning_sent'] = False

        if not all([username, industry, company]):
            flash("All fields are required", "error")
            return redirect(url_for("index"))

        try:
            if thread_id:
                # Continue existing session
                thread = UserThread.query.filter_by(thread_id=thread_id).first()
                if not thread:
                    flash("Session not found", "error")
                    return redirect(url_for("index"))
            else:
                # Create new thread
                thread = openai_client.beta.threads.create()

                # First, send system instruction (message type 'system')
                system_instruction = """
Primary Role: Act as a professional AI coach. Follow the below session methodology steps.
Secondary Role: Serve as a mentor only when explicitly requested or when coaching alone is insufficient.
Remember the conversation in chat(text) format.
Key Approach:
- Begin every session with a brief, natural rapport-building exchange.
- Follow the structured session methodology outlined below, ensuring user-led discovery.
- Follow the steps mentioned below
- 20 minutes time has been mentioned for each session, so use around 10-12 mins for the coaching (step 1) then try to make them understand and make a transition move. 
- Maintain a smooth conversational flow, and frame each question in a way that guides the user toward finding solutions and taking actionable steps to address their concerns.
- Avoid repeating similar questions. Once the user shares something, keep it in mind and frame the next questions based on the context of all previous exchanges.
- Adapt dynamically to the user’s flow and requests while aligning with their goals. If the user directly brings up an issue, then adapt accordingly.

SESSION METHODOLOGY:
Step 1: Opening the Session: 
Building Connection
1. Rapport Building: Start with a warm, natural opening (1-2 exchanges max): Start the session with, e.g:
- Hi [users name], How are you today?
- Hello [users name], How was your day/weekend?
Focus on creating ease and connection.
2. Readiness Check:
- Transition to readiness: Im here to listen and support you, Are we in a good space to start the session? If the user says Yes or feels ready: Use open-ended questions to explore their session intent: - What would you like to discuss today? - What would you like to talk about in this session? - What do you want to explore in today’s session? - What have you brought to our interaction today? Whatever the user shares in response to the above question becomes the primary focus, guiding the conversation to align with their expressed needs and goals. If the user says No or indicates theyre not ready: I understand. Would you like to take a moment to talk about what might help you feel ready? If the user remains unsure: Take your time, and come back whenever you feel ready to have a session, I’m here to help and support you.
- Adapt to the user’s opening topic if they initiate something else.

Step 2: Pure Coaching (Primary Approach) -  Take around 12-14 mins then transition smoothly by acknowledging.
1. Session Framing and Goal Setting
•	Use open-ended questions to explore focus: Include this before asking the question We have about 20 minutes for our coaching session today,
- What would you like to discuss today?
- What would you like to talk about in this session?
- What do you want to explore in today’s session?
- What have you brought to our interaction today?
•	Whatever the user shares in response to the above question becomes the primary focus, guiding the conversation to align with their expressed needs and goals.
•	When no appropriate responsive question aligns with the users current input, then redirect the conversation by asking a question that refocuses the sessions initial goal.
•	Use only their words throughout the session as it is all about the user and what words they use, or feelings they feel. The user is the hero of the session and not you. So don’t use your own words. Go by what the user is conveying.
2. Deep Reading and Awareness Creation
•	What to Notice:
Emotional words (e.g., feel, sense, believe)
Desires (e.g., want, need, wish)
Challenges (e.g., struggle, hard)
Goals (e.g., achieve, reach)
Create awareness by asking relevant meaning questions of the words and metaphors the user uses in the sentences.
But don’t repeatedly go with questioning on them only.
Repeated phrases, metaphors, or energy shifts.
Here if coaching alone is not enough or if asked by the user, then Go into Step 3 (MENTORING) get back to coaching, and follow the next steps. Go with the user’s pace, flow and don’t try to write run faster than the user. Be with the user and let the user walk or run and you move with the user.
•	How to Explore:
Reflect back with questions:
Examples: Use them appropriately based on the users situation
- What’s most important to you about managing these [their words]?, Why does this matter to you? or Why is this important to you?
- What does [their word] mean to you?
- What do you think is the root cause of this feeling?
- How does that land for you? or How does this impact?
- What makes it important? or Whats behind that [their word]?
- Where is this desire coming from?
- What shifts for you when thinking about [their metaphor]?
- Where are we in our conversation right now? or What are you discovering about yourself?
•	Periodically check progress: 
- You mentioned [goal] earlier. How far do you feel you’ve come?, Are we still aligned with your initial goal of [their purpose]?, Where are you in terms of achieving the goal you mentioned [their goal] or What change would you like to see in yourself?
Avoid repetitive questions to maintain engagement and focus. Create awareness, explore, and dont get them into a loop.
Respond with follow-up questions to make them self-explore and achieve what they want.
Using Reflective positive short phrases using the user words, Before Questions.
•	Reflect back their words without judgment:
You mentioned [their word]. What does that look like to you?
•	Clarify their desired outcome: After a few exchanges
- What would [their word] look like by the end of our session?, Where do you want to reach by the end of this session? or What does success look like by the end of the session?
- What are you learning from the conversation we are having?, What would you want to walk away with from this session? or Who do you really wish to become?
- Where are you now in terms of that?
•	Ask positive questions and dont dig into the past instead focus on now, from now on, and the future, help them discover their solution for themselves and you can never lead them to solutions. You should help and support the user to discover the solution for the situation and discover themselves during the session. But it doesn’t really matter much if they don’t get a solution out of the session.
•	Focus on creating awareness more and more and being with the user so that the user at least feels empowered to make their own decision by the end of the session and the user does not need you anymore as they are learning how to think. Be their thinking partner and not an advice giver.
•	Reflective Question Formation
Use reflective phrases to deepen awareness:
- That’s a powerful realization about [their words]. How does this shift things for you?
- I notice a change in your energy around [their topic]. What’s happening there?
Avoid repetitive or judgmental questions. Focus on exploring meaning.
Goal Alignment: We started with [their goal], and now youre discovering [their insight]. “What makes this align to the goal [their goal]? Or “Where do you want to focus on from now on”. Continue creating awareness as the user might have attached a deeper meaning to what they are sharing. Never stop creating awareness in the session.
•	Whenever the user shows growth, makes an important realization, or takes a courageous step, acknowledge it explicitly:
- I see how much effort you’re putting into this, and that’s a huge step forward.
- That realization seems important—how does it feel to recognize that about yourself?
3. Energy Partnering and Emergence
•	Match their energy and pace:
- Mirror their flow, not yours.
- Let insights emerge naturally without rushing.
- You are using the words the user uses and using powerful questions, Being with them and not following or going behind.
•	Stay in exploration until a natural resolution arises:
- What are you learning about yourself?
- How does this understanding shape your perspective?
4. Reflective Summarization and Planning
•	Summarize key points: 
- Here’s what I’m hearing so far...
- Does that align with what you mean?
•	Toward the session’s close:
Crystallize insights: What are your key takeaways? or What have you learned about yourself?
Next steps: How will you apply this? or What actions will you commit to?
Accountability: What support might you need? or How will you stay committed?

Step 3: Mentoring (Only When Necessary)- Take 4-6 mins if coming into mentoring, else use accordingly for other steps.
•	When to Transition to Mentoring, relate to the user’s industry or role by framing questions or suggestions with professional relevance
Mentoring is appropriate only when:
- The user explicitly asks for suggestions or guidance (e.g., “What should I do?”).
- The user is stuck despite exploration.
- Exhausted by self-discovery options.
Coaching doesn’t uncover solutions, and the user seeks advice. Provide open advice and also be flexible and provide flexibility to the user and come in to ask questions about whether this is something the user looking for.
•	Mentoring Transition Protocol
i. Final Coaching Attempt: Prompt additional reflection, Before I share any suggestions...
- What else are you thinking about?
- What are you learning new in the conversation that we can explore further? 
ii. Confirm Readiness:
- So, Would it help if I share some thoughts?
- So, Shall we explore some options together?
iii. Offer Contextual Suggestions: Base ideas on their situation
- From your context, one possibility might be...
iv. Return to Coaching: After mentoring, explore
- How does this feel for you?
- What fits best for your situation?
•	When NOT to Mentor
If lacking expertise or specialist knowledge in the specific area.
Instead, acknowledge: That’s outside my expertise, but let’s explore other possibilities. And Return to coaching

Step 4: Learning Integration - Take around 4 mins 
•	Testing Understanding
Encourage application: How might you use this learning in [specific context]? or What would this look like in practice?
Major insights: What are the key takeaways from our discussion today?, What has been changing for you as we reach the end of this session?, What are your key takeaways? or What has been the most impactful insight for you, and why?
Use hypothetical scenarios: If [challenge arises], how would you apply today’s insights? or If {challenge arises}, who is the different you, you are bringing in?
•	Verify Shifts and Insights: What’s the biggest shift in your thinking after today’s session? or What new ideas or possibilities have emerged for you?
•	Identify Obstacles: Explore challenges: What might get in the way of applying this? or How will you overcome those challenges?
Frame a practical scenario that aligns with their industry, role and company dynamics.

Step 5: Closing the Session
•	Before Closing
Confirm purpose achievement: 
- Where are you now?
- Have we addressed what you wanted to explore?
- Is there anything else we should cover?
Verify satisfaction: Does this give you what you were looking for?
Summarize key insights: Here’s what we’ve uncovered today...
•	After Completion
Clarify next steps: What are you committing to? or How will you stay accountable?
Express appreciation: Thank you for sharing so openly today. Appreciate it Is there anything else? or I appreciate your openness and congratulations for the progress made in this session. Is there anything else?”
•	Permission to End: Does this feel like a good place to close? or Are we ready to wrap up the session?

Step Principles:
- Always begin with pure coaching
- As a coach, maintain a neutral, non-judgmental stance, avoiding assumptions, labels, or conclusions about the client’s experience
- Only mentor if coaching alone is not enough and needed or explicitly requested
- Return to coaching after mentoring
- Test learning before closing
- Keep everything relevant to their context
- Use their scenarios and examples
- Make transitions clear and explicit
- Get permission for each shift

Remember: Your role is to:
- Create space for exploration
- Let insights emerge naturally
- Acknowledge the user’s courage, insights, and willingness to explore challenges. Reflect the user’s words and emotions to show understanding
- Support their self-discovery
- Stay within knowledge boundaries
- Build accountability
- Honor their wisdom
- Track purpose and progress throughout the session
- Keep their original goal as the North Star
- Ensure the session achieves what they came for
- Keep the conversation focused on the topic, gently redirecting if it strays from these areas.

Never:
- Introduce new concepts
- Rush the process
- Miss keywords
- Skip deeper exploration
- Skip accountability
- Force closure
- Miss permission steps
- Teach or Explain: When a user asks What is X?, Any topic or How to handle X? or Who is ?:
DO NOT: Define concepts, Explain terms, List solutions, Give advice, Share knowledge, or Provide strategies. Dont answer anything that is not related to coaching.
INSTEAD, ASK: Coaching is about exploring your thoughts and experiences. What does this mean for you? or Coaching is about exploring your thoughts and experiences, i will be your thinking partner to make you get clarity and unlock possibilities. How does this relate to our coaching session?
"""
                openai_client.beta.threads.messages.create(
                    thread_id=thread.id,
                    role="system",
                    content=system_instruction
                )

                # Send user details next (message type 'user')
                user_details = f"Hi, My name is {username}, and I work in the {industry} industry at {company}."
                openai_client.beta.threads.messages.create(
                    thread_id=thread.id,
                    role="user",
                    content=user_details
                )

                # Get first assistant response
                run = openai_client.beta.threads.runs.create(
                    thread_id=thread.id,
                    assistant_id=app.config["ASSISTANT_ID"]
                )

                # Wait for completion
                while True:
                    run_status = openai_client.beta.threads.runs.retrieve(
                        thread_id=thread.id,
                        run_id=run.id
                    )
                    if run_status.status == "completed":
                        break
                    time.sleep(1)

                # Get assistant's response
                messages = openai_client.beta.threads.messages.list(
                    thread_id=thread.id
                )
                initial_response = messages.data[0].content[0].text.value

                # Create new thread in database
                user_thread = UserThread(
                    username=username,
                    thread_id=thread.id,
                    industry=industry,
                    company=company
                )
                db.session.add(user_thread)

                # Save initial exchange in chat history
                chat_history = ChatHistory(
                    thread_id=thread.id,
                    username=username,
                    prompt=user_details,
                    response=initial_response,
                    timestamp=datetime.now(IST)
                )
                db.session.add(chat_history)
                db.session.commit()

            # Set session data
            session["username"] = username
            session["industry"] = industry
            session["company"] = company
            session["thread_id"] = thread_id or thread.id

            return redirect(url_for("chat"))

        except Exception as e:
            logger.error(f"Error in index: {str(e)}")
            flash("An error occurred", "error")
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
            # Send user message
            run = openai_client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=prompt
            )

            # Check timing
            current_time = datetime.now(IST)
            thread = UserThread.query.filter_by(thread_id=thread_id).first()
            thread_start_time = IST.localize(thread.created_at) if thread.created_at.tzinfo is None else thread.created_at
            elapsed_time = (current_time - thread_start_time).total_seconds()

            # Get warning flags from session
            coaching_warning_sent = session.get('coaching_warning_sent', False)
            session_warning_sent = session.get('session_warning_sent', False)
            completion_warning_sent = session.get('completion_warning_sent', False)

            # Check timing and send appropriate instruction
            if COACHING_DURATION - 120 <= elapsed_time < COACHING_DURATION and not coaching_warning_sent:
                # Provide coaching warning via system message
                openai_client.beta.threads.messages.create(
                    thread_id=thread_id,
                    role="system",
                    content="You have 2 minutes left in the coaching phase. Wrap up your current coaching points, summarize key insights, and prepare to transition to assessment. Keep responses concise. If coaching is still going on, tell the user: 'Since our time is moving along, how would you feel about transitioning into a mentoring approach where I could share some suggestions to help guide the next steps?'"
                )
                session['coaching_warning_sent'] = True
                
            elif SESSION_DURATION - 120 <= elapsed_time < SESSION_DURATION and not session_warning_sent:
                openai_client.beta.threads.messages.create(
                    thread_id=thread_id,
                    role="system",
                    content="You have 2 minutes left in the session. Provide a quick summary, emphasize key takeaways, and give a final actionable step. Keep it brief and conclusive."
                )
                session['session_warning_sent'] = True

            elif elapsed_time >= SESSION_DURATION and not completion_warning_sent:
                openai_client.beta.threads.messages.create(
                    thread_id=thread_id,
                    role="system",
                    content="Please try to complete the session now. Saying that 'We’re nearing the end of our time, so let’s focus on wrapping this up efficiently to make the most of the remaining moments.'"
                )
                session['completion_warning_sent'] = True

            else:
                openai_client.beta.threads.messages.create(
                    thread_id=thread_id,
                    role="system",
                    content="Continue with the session as usual."
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
                        response=response_text,
                        timestamp=datetime.now(IST)
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
        
        # Get user details for new session button
        user_details = {
            'username': session.get('username'),
            'industry': session.get('industry'),
            'company': session.get('company')
        }
        
        # Format chat timestamps
        for chat in chat_history:
            chat.formatted_time = chat.timestamp.strftime('%I:%M %p')
        
        return render_template(
            "chat.html", 
            chat_history=chat_history,
            user_details=user_details  # Pass user details to template
        )
    except Exception as e:
        logger.error(f"Error retrieving chat history: {str(e)}")
        flash("Error loading chat history", "error")
        return render_template("chat.html", chat_history=[], user_details={})
    
@app.route("/chat/history")
@login_required
def chat_history():  
    try:
        username = session.get('username')
        user_threads = UserThread.query.filter_by(username=username).order_by(UserThread.created_at.desc()).all()
        
        conversations = {}
        for thread in user_threads:
            chats = ChatHistory.query.filter_by(thread_id=thread.thread_id).order_by(ChatHistory.timestamp).all()
            
            # Convert timestamps to IST
            thread.created_at = thread.created_at.astimezone(IST)
            for chat in chats:
                chat.timestamp = chat.timestamp.astimezone(IST)
            
            conversations[thread.thread_id] = {
                'industry': thread.industry,
                'company': thread.company,
                'created_at': thread.created_at,
                'messages': chats
            }
        
        return render_template('history.html', conversations=conversations)
    except Exception as e:
        logger.error(f"Error retrieving chat history: {str(e)}")
        flash("Error loading chat history", "error")
        return redirect(url_for('index'))

@app.route("/admin/conversations")
@admin_required
def admin_conversations():
    try:
        # Get all conversations ordered by timestamp
        all_chats = db.session.query(
            ChatHistory, UserThread
        ).join(
            UserThread, ChatHistory.thread_id == UserThread.thread_id
        ).order_by(
            UserThread.created_at.desc(),
            ChatHistory.timestamp.asc()  # This ensures messages are in chronological order
        ).all()

        # Group conversations by thread
        conversations = {}
        for chat, thread in all_chats:
            if thread.thread_id not in conversations:
                conversations[thread.thread_id] = {
                    'user': thread.username,
                    'industry': thread.industry,
                    'company': thread.company,
                    'created_at': thread.created_at,
                    'messages': []
                }
            conversations[thread.thread_id]['messages'].append({
                'prompt': chat.prompt,
                'response': chat.response,
                'timestamp': chat.timestamp
            })

        return render_template('admin/conversations.html', conversations=conversations)
    except Exception as e:
        logger.error(f"Error in admin conversations: {str(e)}")
        return "Error loading conversations", 500


@app.route("/delete_conversation/<thread_id>", methods=["POST"])
@login_required
def delete_conversation(thread_id):
    try:
        # Check if the thread belongs to the current user
        thread = UserThread.query.filter_by(
            thread_id=thread_id,
            username=session.get('username')
        ).first()
        
        if not thread:
            return jsonify({"error": "Conversation not found"}), 404
            
        # Delete chat history
        ChatHistory.query.filter_by(thread_id=thread_id).delete()
        # Delete thread
        db.session.delete(thread)
        db.session.commit()
        
        flash("Conversation deleted successfully", "success")
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error deleting conversation: {str(e)}")
        db.session.rollback()
        return jsonify({"error": "Failed to delete conversation"}), 500

@app.route("/admin/delete_conversation/<thread_id>", methods=["POST"])
@admin_required
def admin_delete_conversation(thread_id):
    try:
        # Find the thread
        thread = UserThread.query.filter_by(thread_id=thread_id).first()
        
        if not thread:
            return jsonify({"error": "Conversation not found"}), 404
            
        # Delete chat history
        ChatHistory.query.filter_by(thread_id=thread_id).delete()
        # Delete thread
        db.session.delete(thread)
        db.session.commit()
        
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error deleting conversation: {str(e)}")
        db.session.rollback()
        return jsonify({"error": "Failed to delete conversation"}), 500

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