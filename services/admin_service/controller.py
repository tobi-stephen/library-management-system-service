from init_svc import *


@app.get('/users')
@admin_required()
def get_users():
    logging.info('getting users')
    
    identity = get_jwt_identity()
    page = int(request.args.get('page', 0))
    size = int(request.args.get('size', 10))

    user_list = list(
        user_collection.find(
            {}, 
            projection={'_id': 0, 'password': 0},
            skip=page*size,
            limit=size,
            sort=[('name', pymongo.ASCENDING)]
        ))

    return jsonify(identity=identity, data=user_list)


@app.get('/users/<user_guid>')
@admin_required()
def get_user(user_guid):
    logging.info('getting user')
    
    identity = get_jwt_identity()

    user = user_collection.find_one(
            {'guid': user_guid}, 
            projection={'_id': 0, 'password': 0})

    if not user:
        return jsonify(msg='user not exists'), 400

    return jsonify(identity=identity, data=user)


@app.put('/users/<user_guid>')
@admin_required()
def update_user(user_guid):
    logging.info('update user')
    
    user_exist = user_collection.find_one({'guid': user_guid})
    if not user_exist:
        return jsonify(msg='invalid request'), 400

    identity = get_jwt_identity()
    data = request.json
    try:
        user_dump = UserUpdate(**data).model_dump()
    except ValidationError:
        return jsonify(msg='invalid request'), 400

    now = datetime.datetime.now()
    user = {
        'name': user_dump.get('name'),
        'email': user_dump.get('email'),
        'phone_number': user_dump.get('phone_number'),
        'address': user_dump.get('address'),
        'activated': user_dump.get('activated'),
        'role': user_dump.get('role'),
        'likes': user_dump.get('likes'),
        'profile_img': user_dump.get('profile_img'),
        'new_book_notification': user_dump.get('new_book_notification'),
        'date_modified': now
    }

    try:
        user_collection.find_one_and_update(
            {'guid': user_guid},
            {'$set': user})
    except pymongo.errors.DuplicateKeyError:
        return jsonify(msg='user already exists'), 400

    # TODO: use email service
    threading.Thread(target=send_profile_update_mail, args=(user,)).start()

    return jsonify(identity=identity, msg='user updated'), 200


@app.delete('/users/<string:user_guid>')
@admin_required()
def delete_user(user_guid):
    identity = get_jwt_identity()

    user_collection.delete_one({'guid': user_guid})

    return jsonify(identity=identity), 204
