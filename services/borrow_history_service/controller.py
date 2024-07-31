from init_svc import *


@app.get('/history')
@jwt_required()
def get_history():
    logging.info('getting borrow history')
    
    identity = get_jwt_identity()
    page = int(request.args.get('page', 0))
    size = int(request.args.get('size', 10))
    filter_query = {  # TODO: expand to support search by different fields
        'user_guid': identity.get('guid'),
    }

    history_list = list(
        history_collection.find(
            filter_query, 
            projection={'_id': 0},
            skip=page*size,
            limit=size,
            sort=[('date_created', pymongo.ASCENDING)]
        ))

    return jsonify(identity=identity, data=history_list)


@app.get('/history/<string:history_guid>')
@jwt_required()
def get_history_by_guid(history_guid):
    logging.info('getting borrow history by guid')
    
    identity = get_jwt_identity()

    history_result = history_collection.find_one(
            {'guid': history_guid, 'user_guid': identity.get('guid')}, 
            projection={'_id': 0}
        )
    
    if not history_result:
        return jsonify(msg='invalid history id'), 400

    return jsonify(identity=identity, data=history_result)


@app.post('/borrow')
@jwt_required()
def borrow_book():
    logging.info('borrow a book')
    
    identity = get_jwt_identity()
    data = request.json | {'user_guid': identity.get('guid')}

    try:
        book_dump = UserBookModel(**data).model_dump()
    except ValidationError:
        return jsonify(msg='invalid request data')
    
    existing_book: dict = book_collection.find_one(
            {'guid': book_dump.get('book_guid')},
            projection={'_id': 0})

    if not existing_book:
        return jsonify(msg='book not exists'), 400
    
    if not existing_book.get('available') or existing_book.get('reserved'):
        return jsonify(msg='book not available'), 400
    
    guid = str(uuid.uuid4())
    now = datetime.datetime.now()

    # For successful borrow, we update the collections: `history` and `books`
    borrow_history = {
        'guid': guid,
        'book_guid': book_dump.get('book_guid'),
        'user_guid': book_dump.get('user_guid'),
        'applicable_fee': LATE_FEE,
        'renews': 0,
        'status': 'ACTIVE',
        'returned': False,
        'fine_paid': 0,
        'expected_return_date': now + datetime.timedelta(minutes=2),
        'date_created': now,  # also used as `date_borrowed`
        'date_returned': None,
        'date_modified': now,
        'date_renewed': None
    }

    # TODO: test using a replica set mongo
    # with mongo.cx.start_session() as session:
    #     with session.start_transaction():
    #         history_collection.insert_one(borrow_history, session=session)
    #         book_collection.update_one(
    #             {'guid': book_dump.get('book_guid')},
    #             {'$set': {
    #                 'available': False
    #             }})

    history_collection.insert_one(borrow_history)
    del borrow_history['_id']
    book_collection.update_one(
        {'guid': book_dump.get('book_guid')},
        {'$set': {
            'available': False
        }})


    return jsonify(identity=identity, data=borrow_history)


@app.post('/return')
@jwt_required()
def return_book():
    logging.info('return a book')
    
    identity = get_jwt_identity()
    data = request.json

    history_guid = data.get('history_guid')

    history_result = history_collection.find_one(
            {'guid': history_guid}, 
            projection={'_id': 0}
        )
    if not history_result:
        return jsonify(msg='invalid history id'), 400
    
    if history_result.get('status') != 'ACTIVE':  # request might be a duplicate return
        return jsonify(identity=identity, data=history_result)
    
    # For successful return, we update the collections: `history` and `books`
    now = datetime.datetime.now()
    exp_ret_date: datetime.datetime = history_result.get('expected_return_date')
    accrued_fine = 0
    if exp_ret_date < now:  # return is late
        total_seconds = (now - exp_ret_date).total_seconds()
        accrued_fine = history_result.get('applicable_fee') * (total_seconds/60)

    borrow_history = {
        'status': 'CLOSED' if accrued_fine == 0 else 'FINED',
        'returned': True,
        'date_returned': now,
        'date_modified': now,
    }

    # with mongo.cx.start_session() as session:
    #     with session.start_transaction():
    #         history_result = history_collection.find_one_and_update(
    #             {'guid': history_result.get('guid')},
    #             {'$set': borrow_history},
    #             projection={'_id': 0},
    #             return_document=pymongo.ReturnDocument.AFTER
    #             session=session)
    #         book_collection.update_one(
    #             {'guid': history_result.get('book_guid')},
    #             {'$set': {
    #                 'available': True
    #             }})

    history_result = history_collection.find_one_and_update(
        {'guid': history_result.get('guid')},
        {'$set': borrow_history},
        projection={'_id': 0},
        return_document=pymongo.ReturnDocument.AFTER)
    
    book_collection.update_one(
        {'guid': history_result.get('book_guid')},
        {'$set': {
            'available': True
        }})
    
    # TODO: notify users of book availability, if `reserved`

    return jsonify(identity=identity, data=history_result)


@app.post('/renew')
@jwt_required()
def renew_book():
    logging.info('renew a borrowed book')
    
    identity = get_jwt_identity()
    data = request.json

    history_guid = data.get('history_guid')

    history_result = history_collection.find_one(
            {'guid': history_guid}, 
            projection={'_id': 0}
        )
    if not history_result:
        return jsonify(msg='invalid history id'), 400
    
    if history_result.get('status') != 'ACTIVE':
        return jsonify(msg='can not renew non-active resource'), 400
    
    now = datetime.datetime.now()
    if history_result.get('expected_return_date') < now:
        return jsonify(msg='return overdue'), 400
    
    existing_book: dict = book_collection.find_one(
            {'guid': history_result.get('book_guid')},
            projection={'_id': 0})

    if not existing_book:
        return jsonify(msg='book not exists'), 400
    
    if existing_book.get('reserved'):
        return jsonify(msg='book not available'), 400
    
    history_result = history_collection.find_one_and_update(
        {'guid': history_guid},
        {'$set': {
            'renews': history_result.get('renews') + 1,
            'expected_return_date': now + datetime.timedelta(minutes=2),
            'date_renewed': now,
            'date_modified': now,
        }},
        projection={'_id': 0},
        return_document=pymongo.ReturnDocument.AFTER
    )

    return jsonify(identity=identity, data=history_result)


@app.get('/fines')
@jwt_required()
def get_history_fines():
    logging.info('getting fines from borrow history')
    
    identity = get_jwt_identity()
    page = int(request.args.get('page', 0))
    size = int(request.args.get('size', 10))

    # find history where the `borrow` is not CLOSED, passed the expected return date
    filter_query = {
        'status': {'$not': {'$eq': 'CLOSED'}},
        'expected_return_date': {'$lt': datetime.datetime.now()},
        'user_guid': identity.get('guid')
    }

    history_list = list(
        history_collection.find(
            filter_query, 
            projection={'_id': 0},
            skip=page*size,
            limit=size,
            sort=[('date_created', pymongo.ASCENDING)]
        ))

    return jsonify(identity=identity, data=history_list)