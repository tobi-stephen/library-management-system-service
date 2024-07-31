from init_svc import *


@app.post('/register')
def register():
    logging.info('register user')
    
    data = request.json
    try:
        user_dump = UserSignup(**data).model_dump()
    except ValidationError:
        return jsonify(msg='invalid request'), 400

    now = datetime.datetime.now()
    user = {
        'name': user_dump.get('name'),
        'email': user_dump.get('email'),
        'phone_number': user_dump.get('phone_number'),
        'password': generate_password_hash(user_dump.get('password')),
        'guid': str(uuid.uuid4()),
        'activated': True if app.config['DEBUG'] else False,
        'role': 'regular',
        'date_created': now,
        'date_modified': now
    }

    try:
        user_collection.insert_one(user)
    except pymongo.errors.DuplicateKeyError:
        return jsonify(msg='user already exists'), 400

    # TODO: use email service
    threading.Thread(target=send_activation_mail, args=(user,)).start()

    return jsonify(msg='user registered, see email for activation'), 200


@app.get('/activate/<string:encoded_activation>')
def activate(encoded_activation: str):
    logging.info('activate user: ' + encoded_activation)
    
    try:
        payload: dict = jwt.decode(encoded_activation, ACTIVATION_SECRET_KEY, algorithms=[ACTIVATION_JWT_ALGO])
    except jwt.ExpiredSignatureError:
        return jsonify(msg='activation link expired')

    email = payload.get('email')
    user: dict = user_collection.find_one({'email': email})

    if not user:
        return jsonify(msg='invalid user'), 400

    if user.get('activated'):
        return jsonify(msg='user already activated'), 400
    
    now = datetime.datetime.now()
    user_collection.update_one(
        {'email': email}, 
        {'$set': {
            'activated': True,
            'likes': [],
            'address': None,
            'profile_img': None,
            'date_modified': now
        }})

    return jsonify(msg='user activated'), 201


@app.post('/login')
def login():
    data: dict = request.json
    email = data.get('email', None)
    password = data.get('password', None)
    if not email or not password:
        return jsonify(msg='invalid request'), 401
    
    user: dict = user_collection.find_one({'email': email})
    if not user or not check_password_hash(user.get('password'), password):
        return jsonify(msg='invalid email/password'), 401
    
    if not user.get('activated'):
        # TODO: use email service
        threading.Thread(target=send_activation_mail, args=(user,)).start()
        return jsonify(msg='check your email to activate your account'), 401

    identity = {
        'email': email,
        'guid': user.get('guid')
    }
    access_token = create_access_token(identity=identity, additional_claims={'role': user.get('role')})
    refresh_token = create_refresh_token(identity='example_user')
    return jsonify(access_token=access_token, refresh_token=refresh_token)


@app.post('/reset_password')
def reset_password():
    data: dict = request.json

    email = data.get('email', None)
    if not email:
        return jsonify(msg='invalid request, email missing'), 401
    
    user: dict = user_collection.find_one({'email': email})
    if not user:
        return jsonify(msg='invalid email'), 401
    
    # TODO: use email service
    threading.Thread(target=send_reset_mail, args=(user,)).start()

    return jsonify(msg='check your email to reset your password'), 200


@app.get('/reset_password/<string:encoded_reset_payload>')
def start_reset_password(encoded_reset_payload: str):
    try:
        decoded_reset: dict = jwt.decode(encoded_reset_payload, RESET_SECRET_KEY, [RESET_JWT_ALGO])
    except jwt.ExpiredSignatureError:
        return jsonify(msg='reset link expired')
    
    email = decoded_reset.get('email')

    return jsonify(email=email)


@app.post('/reset_password/<string:encoded_reset_payload>')
def complete_reset_password(encoded_reset_payload: str):
    try:
        decoded_reset: dict = jwt.decode(encoded_reset_payload, RESET_SECRET_KEY, [RESET_JWT_ALGO])
    except jwt.ExpiredSignatureError:
        return jsonify(msg='reset link expired')
    
    decoded_email = decoded_reset.get('email')

    data: dict = request.json

    email = data.get('email', None)
    password = data.get('password', None)

    if not email or not password or decoded_email != email:
        return jsonify(msg='invalid request'), 401
    
    now = datetime.datetime.now()
    user: dict = user_collection.find_one_and_update(
        {'email': email},
        {'$set': {
            'password': generate_password_hash(password),
            'date_modified': now
        }})
    if not user:
        return jsonify(msg='invalid email'), 401
    
    # TODO: use email service
    threading.Thread(target=reset_completed_mail, args=(user,)).start()

    return jsonify(msg='password reset complete'), 401


@app.route('/token/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    identity = get_jwt_identity()
    access_token = create_access_token(identity=identity, fresh=False)
    return jsonify(access_token=access_token)


@app.get('/profile')
@jwt_required()
def get_profile():
    current_user = get_jwt_identity()
    user = user_collection.find_one(
        {'guid': current_user.get('guid')}, 
        projection={'_id': 0, 'password': 0})
    return jsonify(identity=current_user, data=user), 200


@app.post('/profile')
@jwt_required()
def update_profile():
    current_user = get_jwt_identity()

    data = request.json
    try:
        profile_update = ProfileUpdate(**data).model_dump()
    except ValidationError:
        return jsonify(msg='invalid request data'), 400
    
    user_profile = {
        **profile_update,
        'date_modified': datetime.datetime.now()
    }

    try:
        user = user_collection.find_one_and_update(
            {'guid': current_user.get('guid')},
            {'$set': user_profile},
            projection={'_id': 0, 'password': 0},
            return_document=pymongo.ReturnDocument.AFTER)
    except:
        return jsonify(msg='invalid request, can not update')

    return jsonify(identity=current_user, data=user), 200
