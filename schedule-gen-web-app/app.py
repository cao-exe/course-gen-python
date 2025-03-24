from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from pymongo import MongoClient
from mongoengine import Document, StringField, ListField, ReferenceField, IntField, BooleanField, DateTimeField, connect
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from dotenv import load_dotenv
from itertools import combinations
import os
from calendar_view.calendar import Calendar
from calendar_view.core.config import CalendarConfig
from calendar_view.core.event import Event
from calendar_view.config import style
from bson.dbref import DBRef

from PIL import ImageFont
from pkg_resources import resource_filename

font_path: str = 'Roboto-Regular.ttf'

def image_font(size: int):
    path: str = resource_filename('calendar_view.resources.fonts', font_path)
    return ImageFont.truetype(path, size)

style.event_title_font = image_font(25)
config = CalendarConfig(
    lang='en',
    title='Class Schedule',
    dates='Mo - Fr',
    hours='8 - 20',
    mode=None,
    show_date=False,
    show_year=False,
    legend=False,
)


# MongoEngine Schemas
class User(Document, UserMixin):
    username = StringField(required=True, unique=True)
    password = StringField(required=True)
    schedules = ListField(ReferenceField("Schedule"))
    courses = ListField(ReferenceField("Course"))

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

class Course(Document):
    user = ReferenceField(User, required=True)
    title = StringField(required=True)
    professor = StringField(required=True)
    days = ListField(StringField(), required=True)
    start_time = StringField(required=True)
    end_time = StringField(required=True)
    course_credits = IntField(required=True)
    priority = BooleanField(default=False)
    created_at = DateTimeField(default=datetime.utcnow)

class Schedule(Document):
    user = ReferenceField(User, required=True)
    name = StringField(required=True)
    courses = ListField(ReferenceField(Course))
    priority_count = IntField(default=0)
    total_credits = IntField(default=0)
    created_at = DateTimeField(default=datetime.utcnow)

def create_app(testing=False):
    load_dotenv()

    app = Flask(__name__, template_folder='templates')
    app.secret_key = os.getenv("SECRET_KEY")

    client = MongoClient(os.getenv("MONGO_URI"))
    db = client["schedule_db"]

    app.config['TESTING'] = testing
    
    if not testing:
        connect(
            db=os.getenv('MONGO_DB_NAME'),
            username=os.getenv('MONGO_USERNAME'),
            password=os.getenv('MONGO_PASSWORD'),
            host=os.getenv('MONGO_HOST'),
            authentication_source='admin'
        )

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "login"

    

    ######################### Helper Functions #########################
    # Helper function to parse time strings in "HH:mm" format to minutes
    def parse_time(time_str):
        hours, minutes = map(int, time_str.split(":"))
        return hours * 60 + minutes

    # Helper function to check for time conflicts between two courses
    def has_time_conflict(course1, course2):
        # Check if the courses share any days
        shared_days = set(course1.days).intersection(course2.days)
        if not shared_days:
            return False

        # Convert start and end times to minutes
        start1, end1 = parse_time(course1.start_time), parse_time(course1.end_time)
        start2, end2 = parse_time(course2.start_time), parse_time(course2.end_time)

        # Check for time overlap
        return start1 < end2 and start2 < end1

    # Helper function to generate all valid course combinations
    def get_all_valid_combinations(courses, credit_limit):
        valid_combinations = []

        for r in range(1, len(courses) + 1):
            for combination in combinations(courses, r):
                total_credits = sum(course.course_credits for course in combination)
                if total_credits > credit_limit:
                    continue

                # Check for time conflicts
                if all(not has_time_conflict(course1, course2) for i, course1 in enumerate(combination) for course2 in combination[i+1:]):
                    valid_combinations.append(combination)

        return valid_combinations
    
    # Helper function to generate schedules for a user
    def generate_schedules_for_user(user_id, min_credits, max_credits):
        try:
            # Fetch all courses for the user
            user_courses = Course.objects(user=user_id)

            # Generate all valid combinations under the credit limit without time conflicts
            course_combinations = get_all_valid_combinations(user_courses, max_credits)
            schedules = []

            for i, combination in enumerate(course_combinations):
                # Calculate total credits and priority count
                total_credits = sum(course.course_credits for course in combination)

                # Skip combinations that don't meet the minimum credit requirement
                if total_credits < min_credits:
                    continue

                priority_count = sum(1 for course in combination if course.priority)

                # Create a new schedule document
                schedule = Schedule(
                    user=user_id,
                    name=f"Schedule {i + 1}",
                    courses=[course for course in combination],
                    priority_count=priority_count,
                    total_credits=total_credits,
                    created_at=datetime.utcnow()
                )
                schedule.save()
                schedules.append(schedule)
            return schedules

        except Exception as e:
            print(f"Error generating schedules: {e}")
            raise

    def make_calender(sorted_schedules):
        schedule_count = 0
        for schedule in sorted_schedules:
            calender = Calendar.build(config)
            for course in schedule.courses:
                if isinstance(course, DBRef):
                    course = db.dereference(course)
                print(course.days)
                for day in course.days:
                    if day == "Monday":
                        calender.add_event(day_of_week=0, start=course.start_time, end=course.end_time, title=course.title)       
                    if day == "Tuesday":
                        calender.add_event(day_of_week=1, start=course.start_time, end=course.end_time, title=course.title)
                    if day == "Wednesday":
                        calender.add_event(day_of_week=2, start=course.start_time, end=course.end_time, title=course.title)
                    if day == "Thursday":
                        calender.add_event(day_of_week=3, start=course.start_time, end=course.end_time, title=course.title)
                    if day == "Friday":
                        calender.add_event(day_of_week=4, start=course.start_time, end=course.end_time, title=course.title)
            calender.save("static/schedule"+str(schedule_count)+".png")
            print("Calender saved")
            schedule_count+=1

    @login_manager.user_loader
    def load_user(user_id):
        return User.objects(id=user_id).first()

    ################################ Routes ################################
    @app.route("/")
    def home():
        return redirect(url_for("login"))

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            username = request.form["username"]
            password = request.form["password"]
            if User.objects(username=username).first():
                flash("Username already exists!", "danger")
                return redirect(url_for("register"))
            user = User(username=username)
            user.set_password(password)
            user.save()
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for("login"))
        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form["username"]
            password = request.form["password"]
            user = User.objects(username=username).first()
            if user and user.check_password(password):
                login_user(user)
                return redirect(url_for("dashboard"))
            flash("Invalid username or password!", "danger")
        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        flash("You have been logged out.", "success")
        return redirect(url_for("login"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        user_courses = Course.objects(user=current_user)
        sorted_schedules = Schedule.objects(user=current_user).order_by("-priority_count", "-total_credits")
        return render_template("dashboard.html", courses=user_courses, schedules=sorted_schedules)

    @app.route("/add_course", methods=["GET", "POST"])
    @login_required
    def add_course():
        if request.method == "POST":
            course_data = {
                "user": current_user,
                "title": request.form["title"],
                "professor": request.form["professor"],
                "days": request.form.getlist("days"),
                "start_time": request.form["start_time"],
                "end_time": request.form["end_time"],
                "course_credits": int(request.form["course_credits"]),
                "priority": "priority" in request.form
            }
            course = Course(**course_data)
            course.save()
            current_user.courses.append(course)
            current_user.save()
            flash("Course added successfully!", "success")
            return redirect(url_for("dashboard"))
        return render_template("add_course.html")

    @app.route("/delete_course/<course_id>", methods=["POST"])
    @login_required
    def delete_course(course_id):
        course = Course.objects(id=course_id, user=current_user).first()
        print("Removing " + course.title)
        if course:
            course.delete()
            current_user.courses = [c for c in current_user.courses if not (isinstance(c, DBRef)) and str(c.id) == str(course.id)]
            current_user.save()
            flash("Course deleted successfully!", "success")
        else:
            flash("Course not found!", "danger")
        return redirect(url_for("dashboard"))

    @app.route("/generate_schedules", methods=["POST"])
    @login_required
    def generate_schedules():
        try:
            min_credits = int(request.form.get("min_credits", 0))
            max_credits = int(request.form.get("max_credits", 18))

            # Remove existing schedules for the user
            Schedule.objects(user=current_user).delete()

            # Generate new schedules
            schedules = generate_schedules_for_user(current_user.id, min_credits, max_credits)
            user_courses = Course.objects(user=current_user)
            sorted_schedules = Schedule.objects(user=current_user).order_by("-priority_count", "-total_credits")
            make_calender(sorted_schedules)


            flash(f"Successfully generated {len(schedules)} schedules!", "success")
        except Exception as e:
            flash(f"Error generating schedules: {str(e)}", "danger")

        return redirect(url_for("dashboard"))

    return app

if __name__ == "__main__":
    app = create_app()
    FLASK_PORT = 3000
    app.run(host="0.0.0.0", port=FLASK_PORT, debug=True)
else:
    app = create_app()