import gevent
import gevent.monkey
gevent.monkey.patch_all()
from flask import Flask, render_template, request
from geventwebsocket.handler import WebSocketHandler
from gevent import pywsgi
from flask_sockets import Sockets
from tweepy.streaming import StreamListener
from tweepy import OAuthHandler
from tweepy import Stream
import json

#database related import 
import redis
from flask import Flask
from flask_sqlalchemy import SQLAlchemy


r = Flask(__name__)
sockets = Sockets(r)


r.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'
db = SQLAlchemy(r)


consumer_key = "w4vyjtRo2bjtpRXN1CYir388j"
consumer_secret = "njTBpMsEV5WEcghbZPACN6dMUnwFsmtRuMHYl9Ap30o7SCJZZm"
access_token = "166712207-CnI8lDoEnTNGtSPagViHVHbi8QvLKj5XcHcHF09D"
access_token_secret = "KoGFcQnVmpu4ff8Lu5cTNwjOlRvPFoewlvQbAIDwNsWrC"

# data model for storing tweets
class tweets(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hashTag = db.Column(db.String(80))
    content = db.Column(db.Text)

    def __init__(self, hashTag, content):
        self.hashTag = hashTag
        self.content = content

    def __repr__(self):
        return '<User %r>' % self.hashTag
db.create_all()

redis = redis.StrictRedis(host='localhost', port=6379, db=0)


# live tweet stream which gives stream of ream-time tweet
# of a given hashtag
class MyStreamListener(StreamListener):
    def __init__(self):
        auth = OAuthHandler(consumer_key, consumer_secret)
        auth.set_access_token(access_token, access_token_secret)
        self.stream = Stream(auth, self)
        self.begnning = True
        self.hashTag = ""
        self.element_count = 0
        # batch_size in number of tweets after which 
        # redis data is commit into the sql data base.
        self.batch_size= 10

    def init(self):
        auth = OAuthHandler(consumer_key, consumer_secret)
        auth.set_access_token(access_token, access_token_secret)
        self.stream = Stream(auth, self)

    def add_socket(self, ws):
        self.socket = ws

    def run(self, hashTag):
        try:
            self.begnning = False
            self.hashTag = hashTag
            print "value inside run is => ", hashTag
            self.stream.filter(track=[hashTag], async=True)
        except Exception as e:
            print "DISCONNECTED ", e
            self.stream.disconnect()

    def start(self, hashTag):
        print "value inside start is => ", hashTag
        gevent.spawn(self.run, hashTag)

    def send(self, ws, coordinates):
        try:
            ws.send(json.dumps(coordinates))
        except Exception as e:
            print "something went wrong while sending", e

    def on_data(self, data):
        decoded = json.loads(data)
        # pushing data info redis list.
        redis.rpush(self.hashTag, decoded)
        self.element_count = self.element_count + 1
        # checking if current count is greater than 
        # batch size, if so commit current batch in database.
        if self.element_count > self.batch_size:
            l = redis.lrange(self.hashTag, 0, -1)
            hashTag_exist = tweets.query.filter(tweets.hashTag == self.hashTag).first()
            # check if hashtag exist update the existing row
            if hashTag_exist:
                print "### HashTag Exsits in database###"
                new_content = str(hashTag_exist.content) + str(l)
                hashTag_exist.content = new_content
            # if hash tag is not present create new row
            else:
                # if hashtag doesn't exist create a new db ojbect 
                # add it to the session.
                t = tweets(self.hashTag, str(l))
                db.session.add(t)
            # commit all session changes
            db.session.commit()
            print "adding enteries to database."
            # resetting element_count to zero for next batch
            self.element_count = 0
        gevent.spawn(self.send, self.socket, decoded)
        return True

    def on_error(self, status):
        print "Error", status

    def on_timeout(self):
        print "tweepy timeout.. wait 30 seconds"
        gevent.sleep(30)

    def close(self):
        self.stream.disconnect()

stream_listener = MyStreamListener()

# this hander is to check if database is storeing new value
# it returns all hash tag stored in database uncommenting
# t_list.append(t.content) will return all tween content 
# stored in database.
@r.route('/db')
def dbquery():
    t_list = []
    tweet = tweets.query.all()
    for t in tweet:
        t_list.append(t.hashTag)

        # becareful 'content' lot of data loading it to browser
        # might slow it down.
        # t_list.append(t.content)
    return str(t_list)

@r.route('/search', methods =['POST'])
def ser():
    print "inside /search method"
    val = request.json
    query = val["query"]
    if stream_listener.begnning:
        stream_listener.start(query)
    else:
        # if it's already connected than close and reconnet.
        stream_listener.close()
        stream_listener.init()
        stream_listener.start(query)
    return "success"

# websoocket
@sockets.route('/t')
def app(ws):
    print "route /t is activated"
    stream_listener.add_socket(ws)
    while not ws.closed:
        gevent.sleep(0.1)

# route for home page.
@r.route('/')
def e():
    return render_template('f_socket.html')    

if __name__ == "__main__":
    from gevent import pywsgi
    from geventwebsocket.handler import WebSocketHandler
    server = pywsgi.WSGIServer(('127.0.0.1', 5000), r, handler_class=WebSocketHandler)
    server.serve_forever()
