import os
from pymongo import MongoClient

MONGO_URI = os.getenv("MONGO_URI", "mongodb+srv://eiryfou_db_user:<oNGWlNI89mfcHu7Z>@inf1103.xnf0hqq.mongodb.net/")

client = MongoClient(MONGO_URI)
db = client["my_application"]
collection = db["records"]

class MongoDataManager:
  def __init__(self, mongo_db):
    self.mongo_db = mongo_db
    client = MongoClient(MONGO_URI)
    db = client["my_application"]
    self.collection = db["records"]

  def InsertRecord(self, records):
    for record in records:
      result = self.collection.insert_one(record)
      if result.acknowledged == True:
        print("Insertion Successful")