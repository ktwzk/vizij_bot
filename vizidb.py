import peewee
import config
import datetime


db = peewee.PostgresqlDatabase(
    config.db_url.path[1:],
    user=config.db_url.username,
    password=config.db_url.password,
    host=config.db_url.hostname,
    port=config.db_url.port
)


class User(peewee.Model):
    username = peewee.TextField(unique=True)
    name = peewee.TextField(default='')
    bio = peewee.TextField(default='')
    birthday = peewee.DateTimeField(default=datetime.datetime.now())
    image = peewee.TextField(default=config.placeholder)
    email = peewee.TextField(default='')
    phone = peewee.TextField(default='')

    class Meta:
        order_by = ('username',)
        database = db


class Link(peewee.Model):
    link = peewee.TextField()
    description = peewee.TextField()
    owner = peewee.ForeignKeyField(User, related_name='links')

    class Meta:
        database = db


def db_action(action):
    def db_wrapper(*args, **kwargs):
        db.connect()
        result = action(*args, **kwargs)
        db.close()
        return result
    return db_wrapper


@db_action
def create_tables():
    db.create_tables([User, Link])


@db_action
def create_user(username):
    user, done = User.create_or_get(username=username)
    user.save()


@db_action
def set_name(username, name):
    user = User.get(username=username)
    user.name = name
    user.save()


@db_action
def set_bio(username, bio):
    user = User.get(username=username)
    user.bio = bio
    user.save()


@db_action
def set_birthday(username, date):
    user = User.get(username=username)
    user.birthday = date
    user.save()


@db_action
def set_image(username, image):
    user = User.get(username=username)
    user.image = image
    user.save()


@db_action
def set_email(username, email):
    user = User.get(username=username)
    user.email = email
    user.save()


@db_action
def set_phone(username, phone):
    user = User.get(username=username)
    user.phone = phone
    user.save()


@db_action
def new_link(username, url, description):
    user = User.get(username=username)
    link = Link.create(link=url, description=description, owner=user)
    link.save()


@db_action
def del_link(username, description):
    link = Link.select().where(Link.description == description).get()
    link.delete_instance()


@db_action
def get_links(username):
    user = User.get(username=username)
    links = {}
    for link in user.links:
        links[link.description] = link.link
    return links
