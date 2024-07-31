## Library Management System

The project is a microservice setup of a library management system.

This will empowers users to access library resources easily and allows administrators to manage book collections and user accounts effectively.

### Setups
- For local email server setup, `python3 -m aiosmtpd -n -l localhost:1025`
- for local mongodb setup, `docker run --rm -it --name mongo -p 27017:27017 mongo`
- `python -m venv .venv` and `source .venv/bin/activate`(on MacOS)
- `python services/admin_service/app.py`
- `python services/book_service/app.py`
- `python services/borrow_history_service/app.py`
- `python services/reservation_service/app.py`
- `python services/user_service/app.py`
- load `LMS.postman_collection.json` in PostMan for local testing

### TODO
- use pydantic for more extensive validation
- reduce repeated code
- explore the use of API gateway

### Resources and User Stories
- [MBE library management project](https://projects.masteringbackend.com/projects/build-your-own-library-management-system)