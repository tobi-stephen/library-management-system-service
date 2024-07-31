from init_svc import *


@app.get('/reservations')
@jwt_required()
def get_reservations():
    logging.info('getting reservations')
    
    identity = get_jwt_identity()
    page = int(request.args.get('page', 0))
    size = int(request.args.get('size', 10))
    filter_query = {  # TODO: expand to support search by different fields
        'user_guid': identity.get('guid'),
    }

    reservation_list = list(
        reservation_collection.find(
            filter_query, 
            projection={'_id': 0},
            skip=page*size,
            limit=size,
            sort=[('date_created', pymongo.ASCENDING)]
        ))

    return jsonify(identity=identity, data=reservation_list)


@app.get('/reservations/<string:reservation_guid>')
@jwt_required()
def get_reservation_by_guid(reservation_guid):
    logging.info('getting reservation by guid')
    
    identity = get_jwt_identity()

    reservation_result = reservation_collection.find_one(
            {'guid': reservation_guid}, 
            projection={'_id': 0}
        )
    
    if not reservation_result:
        return jsonify(msg='invalid reservation id'), 400

    return jsonify(identity=identity, data=reservation_result)


@app.post('/reservations')
@jwt_required()
def reserve_book():
    logging.info('reserve a book')
    
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
    
    guid = str(uuid.uuid4())
    now = datetime.datetime.now()

    # For successful reservation, we update the collections: `history` and `books`
    reservation = {
        'guid': guid,
        'book_guid': book_dump.get('book_guid'),
        'user_guid': book_dump.get('user_guid'),
        'date_created': now,  # also used as `date_reserved`
    }

    reservation_collection.insert_one(reservation)
    del reservation['_id']
    book_collection.update_one(
        {'guid': book_dump.get('book_guid')},
        {'$set': {
            'reserved': True
        }}
    )

    return jsonify(identity=identity, msg='reservation created', data=reservation)


@app.delete('/reservations/<string:reservation_guid>')
@jwt_required()
def close_reservation(reservation_guid):
    logging.info('close reservation')
    
    identity = get_jwt_identity()

    result=reservation_collection.delete_one(
            {'guid': reservation_guid, 'user_guid': identity.get('guid')}
        )
    
    return jsonify(msg='reservation closed', data=result.deleted_count)
