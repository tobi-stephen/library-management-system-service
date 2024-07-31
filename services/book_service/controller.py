from init_svc import *


@app.get('/books')
@jwt_required()
def get_books():
    logging.info('getting books')
    
    identity = get_jwt_identity()
    page = int(request.args.get('page', 0))
    size = int(request.args.get('size', 10))
    search_query = request.args.get('q', '')

    filter_query = {'$text': {'$search': search_query}} if search_query else {}

    book_list = list(
        book_collection.find(
            filter_query, 
            projection={'_id': 0, 'description': 0},
            skip=page*size,
            limit=size,
            sort=[('name', pymongo.ASCENDING)]
        ))

    return jsonify(identity=identity, data=book_list)


@app.get('/books/<book_guid>')
@jwt_required()
def get_book(book_guid):
    logging.info('getting a book')
    
    identity = get_jwt_identity()

    book = book_collection.find_one(
            {'guid': book_guid}, 
            projection={'_id': 0})

    if not book:
        return jsonify(msg='book not exists'), 400

    return jsonify(identity=identity, data=book)


@app.post('/books')
@admin_required()
def add_book():
    logging.info('add book')
    
    identity: dict = get_jwt_identity()
    
    data = request.json
    try:
        book_dump = BookModel(**data).model_dump()
    except ValidationError:
        return jsonify(msg='validation error'), 400
    
    now = datetime.datetime.now()
    book_guid = str(uuid.uuid4())
    book_data = {
        'guid': book_guid,
        'title': book_dump.get('title'),
        'author': book_dump.get('author'),
        'genre': book_dump.get('genre'),
        'description': book_dump.get('description'),
        'img_url': book_dump.get('img_url'),
        'available': True,
        'reserved': False,
        'date_created': now,
        'date_modified': now
    }

    book = book_collection.find_one_and_update(
        {'guid': book_guid},
        {'$set': book_data},
        projection={'_id': 0},
        upsert=True,
        return_document=pymongo.ReturnDocument.AFTER)

    if not book:
        return jsonify(msg='invalid request'), 400
    
    # TODO: use email service to notify users `book_added` event
    threading.Thread(target=notify_book_added, args=(book, )).start()

    return jsonify(identity=identity, msg='book added', data=book), 200


@app.put('/books/<string:book_guid>')
@admin_required()
def update_book(book_guid):
    logging.info('update book')
    
    identity = get_jwt_identity()
    
    data = request.json
    try:
        book_dump = BookModel(**data).model_dump()
    except ValidationError:
        return jsonify(msg='validation error'), 400
    
    now = datetime.datetime.now()
    book_data = {
        'title': book_dump.get('title'),
        'author': book_dump.get('author'),
        'genre': book_dump.get('genre'),
        'description': book_dump.get('description'),
        'img_url': book_dump.get('img_url'),
        'available': book_dump.get('available'),
        'reserved': book_dump.get('reserved'),
        'date_modified': now
    }

    book = book_collection.find_one_and_update(
        {'guid': book_guid},
        {'$set': book_data},
        projection={'_id': 0},
        return_document=pymongo.ReturnDocument.AFTER)

    if not book:
        return jsonify(msg='invalid request'), 400

    return jsonify(identity=identity, msg='book updated', data=book), 200


@app.delete('/books/<string:book_guid>')
@admin_required()
def delete_book(book_guid):
    identity = get_jwt_identity()

    book_collection.delete_one({'guid': book_guid})

    return jsonify(identity=identity), 204
