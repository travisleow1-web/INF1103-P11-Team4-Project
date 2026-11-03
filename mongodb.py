import os
from pymongo import MongoClient

# For local development: 'mongodb://localhost:27017/'
# For MongoDB Atlas: 'mongodb+srv://<user>:<password>@cluster.mongodb.net/'
MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://eiryfou_db_user:<oNGWlNI89mfcHu7Z>@inf1103.xnf0hqq.mongodb.net/")

client = MongoClient(MONGO_URI)
db = client["my_application"]
collection = db["records"]

