# NiceGUI Testing Reference

## Table of Contents
1. [Setup](#1-setup)
2. [Screen Tests (Synchronous)](#2-screen-tests-synchronous)
3. [User Tests (Asynchronous)](#3-user-tests-asynchronous)
4. [Multi-User Tests](#4-multi-user-tests)
5. [Element Marks](#5-element-marks)
6. [Common Assertions](#6-common-assertions)
7. [Test Patterns](#7-test-patterns)

---

## 1. Setup

```bash
pip install nicegui[testing] pytest pytest-asyncio
```

```python
# conftest.py
import pytest
from nicegui.testing import Screen, User

# Screen and User fixtures are provided by NiceGUI's pytest plugin
# No additional conftest needed for basic use
```

```python
# pytest.ini or pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

### App under test
```python
# app.py (your application)
from nicegui import ui, app

@ui.page('/')
def index():
    ui.label('Hello World')
    counter = {'n': 0}
    label = ui.label('0')
    ui.button('Click', on_click=lambda: [
        counter.update(n=counter['n'] + 1),
        setattr(label, 'text', str(counter['n']))
    ])
```

---

## 2. Screen Tests (Synchronous)

`Screen` uses Selenium under the hood. Good for DOM interaction tests:

```python
from nicegui.testing import Screen

def test_page_loads(screen: Screen):
    screen.open('/')
    screen.should_contain('Hello World')

def test_button_click(screen: Screen):
    screen.open('/')
    screen.should_contain('0')       # initial count
    screen.click('Click')
    screen.should_contain('1')       # after click

def test_input_and_search(screen: Screen):
    screen.open('/')
    screen.type(screen.find('input'), 'Hello')
    screen.click('Search')
    screen.should_contain('Results for: Hello')

def test_navigation(screen: Screen):
    screen.open('/')
    screen.click('Settings')        # click a link
    screen.should_contain('Settings Page')
    screen.should_not_contain('Home Page')

def test_form_validation(screen: Screen):
    screen.open('/register')
    screen.click('Submit')          # submit empty form
    screen.should_contain('Name is required')
```

### Screen API
```python
# Navigation
screen.open('/')
screen.open('/page?param=value')

# Finding elements
screen.find('Button Text')
screen.find(ui.input)               # by component type
screen.find_by_class('my-class')
screen.find_by_id('element-id')

# Interaction
screen.click('Button Text')
screen.type(screen.find('input'), 'text to type')
screen.wait(2.0)                    # explicit wait (avoid when possible)

# Assertions
screen.should_contain('text')
screen.should_not_contain('text')
screen.should_see(element)
screen.should_not_see(element)
```

---

## 3. User Tests (Asynchronous)

`User` is the preferred modern test API. Each `User` is a simulated browser client:

```python
import pytest
from nicegui.testing import User
from nicegui import ui

@ui.page('/')
def index():
    ui.label('Welcome')
    name = ui.input('Name')
    result = ui.label('Hello, nobody')
    ui.button('Greet', on_click=lambda: result.set_text(f'Hello, {name.value}!'))


async def test_greeting(user: User):
    await user.open('/')
    await user.should_see('Welcome')

    user.find(ui.input).type('Alice')
    user.find('Greet').click()
    await user.should_see('Hello, Alice!')


async def test_empty_name(user: User):
    await user.open('/')
    user.find('Greet').click()
    await user.should_see('Hello, !')  # empty name

    user.find(ui.input).type('Bob')
    user.find('Greet').click()
    await user.should_see('Hello, Bob!')
    await user.should_not_see('Hello, !')
```

### User API
```python
# Navigation
await user.open('/')
await user.open('/page?q=search')

# Finding (returns element reference)
user.find('Button Label')           # by text content
user.find(ui.input)                 # by component type
user.find(ui.button, nth=2)         # second button
user.find('mark-name')              # by .mark() label

# Interaction (synchronous — queues the action)
user.find(ui.input).type('text')
user.find(ui.input).clear()
user.find('Button').click()
user.find(ui.checkbox).click()
user.find(ui.input).trigger('keydown.enter')
user.find(ui.input).trigger('blur')

# Awaitable assertions
await user.should_see('text content')
await user.should_not_see('text content')
await user.should_see(ui.button)
await user.should_not_see(ui.spinner)

# Context manager for scoped search
async with user.open('/') as page:
    await page.should_see('Welcome')
```

---

## 4. Multi-User Tests

Simulate concurrent users to test real-time features:

```python
from nicegui.testing import User, create_user
from nicegui.events import Event

message_event = Event[str]()

@ui.page('/')
def chat_page():
    messages = ui.column()

    @message_event.subscribe
    def on_message(msg: str):
        with messages:
            ui.label(msg)

    inp = ui.input('Message')
    ui.button('Send', on_click=lambda: message_event.emit(inp.value))


async def test_real_time_chat(user: User):
    """Two users see each other's messages."""
    # Open first client
    await user.open('/')

    # Create second client
    user2 = create_user()
    await user2.open('/')

    # User 1 sends a message
    user.find(ui.input).type('Hello from user 1')
    user.find('Send').click()

    # Both users should see it
    await user.should_see('Hello from user 1')
    await user2.should_see('Hello from user 1')

    # User 2 replies
    user2.find(ui.input).type('Reply from user 2')
    user2.find('Send').click()

    await user.should_see('Reply from user 2')
    await user2.should_see('Reply from user 2')
```

### Testing disconnect behavior
```python
async def test_user_count(user: User):
    await user.open('/')
    await user.should_see('1 user online')

    user2 = create_user()
    await user2.open('/')
    await user.should_see('2 users online')
    await user2.should_see('2 users online')

    await user2.disconnect()  # simulate tab close
    await user.should_see('1 user online')
```

---

## 5. Element Marks

Use `.mark()` to label elements for reliable test targeting (avoids fragile text matching):

```python
@ui.page('/dashboard')
def dashboard():
    with ui.card().classes('w-full'):
        ui.label('Total Users').classes('text-sm text-grey-6')
        ui.label('1,234').classes('text-2xl font-bold').mark('total-users-count')

    submit_btn = ui.button('Submit').props('color=primary')
    submit_btn.mark('submit-button')

    error_label = ui.label('').classes('text-red-500').mark('error-message')
    error_label.set_visibility(False)
```

```python
async def test_dashboard_stats(user: User):
    await user.open('/dashboard')
    count_elem = user.find('total-users-count')
    assert count_elem.text == '1,234'


async def test_form_submit(user: User):
    await user.open('/form')
    user.find(ui.input, nth=0).type('')  # empty required field
    user.find('submit-button').click()
    await user.should_see('error-message')  # error visible


async def test_successful_submit(user: User):
    await user.open('/form')
    user.find(ui.input, nth=0).type('Alice')
    user.find('submit-button').click()
    await user.should_not_see('error-message')
    await user.should_see('Saved!')
```

---

## 6. Common Assertions

```python
# Text content
await user.should_see('Hello World')
await user.should_not_see('Error')
await user.should_see('5 items')  # works for partial match

# Component presence
await user.should_see(ui.spinner)       # spinner is visible
await user.should_not_see(ui.spinner)   # spinner gone (loading done)
await user.should_see(ui.dialog)        # dialog opened

# After async operations
user.find('Load Data').click()
await user.should_not_see(ui.spinner)   # waits for spinner to disappear
await user.should_see('Data loaded')

# Navigation
user.find('Settings Link').click()
await user.should_see('Settings')       # URL changed, new content visible
```

---

## 7. Test Patterns

### Testing auth flow
```python
async def test_redirect_to_login(user: User):
    """Unauthenticated users are redirected."""
    await user.open('/dashboard')
    await user.should_see('Sign In')  # redirected to login
    await user.should_not_see('Dashboard')


async def test_login_success(user: User):
    await user.open('/login')
    user.find(ui.input, nth=0).type('alice')
    user.find(ui.input, nth=1).type('secret123')
    user.find('Sign In').click()
    await user.should_see('Welcome, alice')
    await user.should_not_see('Sign In')


async def test_login_failure(user: User):
    await user.open('/login')
    user.find(ui.input, nth=0).type('alice')
    user.find(ui.input, nth=1).type('wrong')
    user.find('Sign In').click()
    await user.should_see('Invalid credentials')
```

### Testing CRUD operations
```python
async def test_add_and_delete_item(user: User):
    await user.open('/items')
    initial_count = len(user.find_all(ui.card))

    # Add
    user.find(ui.input).type('New Item')
    user.find('Add').click()
    await user.should_see('New Item')
    assert len(user.find_all(ui.card)) == initial_count + 1

    # Delete
    user.find('delete-New Item').click()  # marked button
    await user.should_not_see('New Item')
    assert len(user.find_all(ui.card)) == initial_count


async def test_edit_item(user: User):
    await user.open('/items')
    user.find('edit-item-1').click()       # mark on edit button
    await user.should_see(ui.dialog)       # edit dialog opens

    user.find(ui.input).clear()
    user.find(ui.input).type('Updated Name')
    user.find('Save').click()

    await user.should_not_see(ui.dialog)   # dialog closed
    await user.should_see('Updated Name')
```

### Testing real-time updates
```python
import asyncio

async def test_live_counter(user: User):
    await user.open('/counter')
    await user.should_see('0')          # initial value

    # Wait for timer to fire (counter auto-increments)
    await asyncio.sleep(1.1)
    await user.should_see('1')

    await asyncio.sleep(1.0)
    await user.should_see('2')
```

### Testing file upload
```python
import tempfile, os

async def test_file_upload(user: User):
    await user.open('/upload')

    # Create a temp file to upload
    with tempfile.NamedTemporaryFile(suffix='.txt', delete=False, mode='w') as f:
        f.write('Test file content')
        tmp_path = f.name

    try:
        upload = user.find(ui.upload)
        upload.upload_file(tmp_path)
        await user.should_see('Uploaded')
        await user.should_see('test.txt')
    finally:
        os.unlink(tmp_path)
```

### Testing with mocked dependencies
```python
from unittest.mock import AsyncMock, patch

async def test_api_call(user: User):
    mock_data = [{'id': 1, 'name': 'Alice'}]

    with patch('pages.users.fetch_users', return_value=mock_data):
        await user.open('/users')
        await user.should_see('Alice')
        await user.should_not_see(ui.spinner)
```
