import os
from dotenv import load_dotenv
from pymongo import MongoClient

#reads .env file from the current dir and injects variables onto os.environment
load_dotenv()

# Retrieve variables
MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME", "default_db")

if not MONGO_URI:
  raise ValueError("MONGO_URI not found in environment variables.")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

class MongoDataManager:
  def __init__(self):
    client = MongoClient(MONGO_URI)
    db = client["my_application"]
    self.collection = db["records"]

  def InsertRecord(self, records):
    for record in records:
      result = self.collection.insert_one(record)
      if result.acknowledged == True:
        print("Insertion Successful")

MDM = MongoDataManager()
Record = [{
  "Name" : "Marcus",
  "Age" : 10
}]
MDM.InsertRecord(Record)