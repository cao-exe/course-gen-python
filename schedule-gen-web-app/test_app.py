import pytest
from flask import Flask
from flask_login import UserMixin, login_user, logout_user, current_user
from mongoengine import connect, disconnect, Document, StringField, ListField, ReferenceField, IntField, BooleanField, DateTimeField
import mongomock
from app import create_app, User, Course, Schedule

@pytest.fixture(scope='function')
def mock_db():
    # Disconnect any existing connections to avoid conflicts
    disconnect()
    
    # Connect to a mock database using mongomock
    connect('schedule_db', host='localhost', port=27017, mongo_client_class=mongomock.MongoClient, alias='default')
    yield
    disconnect()  # Ensure disconnecting after the test

@pytest.fixture
def app(mock_db):
    # Explicitly pass `TESTING=True` to the app instance
    app = create_app(testing=True)
    app.secret_key = "KEY"
    app.config['WTF_CSRF_ENABLED'] = False  # Disable CSRF protection for testing
    return app

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def init_user():
    # Create a test user
    user = User(username="testuser")
    user.set_password("password123")
    user.save()
    return user

@pytest.fixture
def init_course(init_user):
    # Create a test course for the user
    course = Course(
        user=init_user,
        title="Test Course",
        professor="Prof. Test",
        days=["Monday", "Wednesday"],
        start_time="08:00",
        end_time="09:30",
        course_credits=4,
        priority=True
    )
    course.save()
    return course

def test_register_user(client, init_user):
    response = client.post('/register', data={
        'username': 'newuser',
        'password': 'newpassword'
    })
    assert response.status_code == 302  # Redirect after registration
    assert User.objects(username='newuser').first() is not None

def test_login(client, init_user):
    response = client.post('/login', data={
        'username': 'testuser',
        'password': 'password123'
    })
    assert response.status_code == 302  # Redirect after successful login

def test_login_failure(client, init_user):
    response = client.post('/login', data={
        'username': 'testuser',
        'password': 'wrongpassword'
    })
    assert response.status_code == 200  # Login page should reload
    assert b"Invalid username or password!" in response.data

def test_add_course(client, init_user):
    client.post('/login', data={'username': 'testuser', 'password': 'password123'})
    response = client.post('/add_course', data={
        'title': 'New Course',
        'professor': 'Prof. Smith',
        'days': ['Tuesday', 'Thursday'],
        'start_time': '10:00',
        'end_time': '11:30',
        'course_credits': 4,
        'priority': 'on'
    })
    assert response.status_code == 302  # Redirect after adding the course
    assert Course.objects(title='New Course').first() is not None

def test_delete_course(client, init_user, init_course):
    client.post('/login', data={'username': 'testuser', 'password': 'password123'})
    response = client.post(f'/delete_course/{init_course.id}')
    assert response.status_code == 302  # Redirect after deleting the course
    assert Course.objects(id=init_course.id).first() is None

def test_generate_schedules(client, init_user, init_course):
    client.post('/login', data={'username': 'testuser', 'password': 'password123'})
    response = client.post('/generate_schedules')
    assert response.status_code == 302  # Redirect after generating schedules
    assert Schedule.objects(user=init_user).count() > 0  # Check that schedules were generated
