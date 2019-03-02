import pdb
import json
import pandas as pd
import pickle
import logging

from utils.feature_tools import FeatureTools

from pathlib import Path
from kafka import KafkaConsumer
from utils.messages_utils import append_message, read_messages_count, send_retrain_message, reload_model

logger = logging.getLogger('ml_pipelines')
logger.setLevel(logging.INFO)

KAFKA_HOST = 'localhost:9092'
TOPICS = ['app_messages', 'retrain_topic']
PATH = Path('data/')
MODELS_PATH = PATH/'models'
DATAPROCESSORS_PATH = PATH/'dataprocessors'
MESSAGES_PATH = PATH/'messages'
RETRAIN_EVERY = 50
EXTRA_MODELS_TO_KEEP = 1

dataprocessor = None
consumer = None
model = None


def is_retraining_message(message):
	message = json.loads(msg.value)
	return msg.topic == 'retrain_topic' and 'training_completed' in message and message['training_completed']


def is_application_message(message):
	return msg.topic == 'app_messages'


def predict(message):
	row = pd.DataFrame(message, index=[0])
	row.drop('income_bracket', axis=1, inplace=True)
	trow = dataprocessor.transform(row)
	return model.predict(trow)[0]


def start(model_id, messages_count, batch_id):
	for msg in consumer:
		message = json.loads(msg.value)

		if is_retraining_message(msg):
			model_fname = 'model_{}_.p'.format(model_id)
			model = reload_model(MODELS_PATH/model_fname)
			logger.info("NEW MODEL RELOADED")
			model_id = (model_id + 1) % (EXTRA_MODELS_TO_KEEP + 1)
			

		elif is_application_message(msg):
			pred = predict(message)
			append_message(message, MESSAGES_PATH, batch_id)
			messages_count += 1
			if messages_count % RETRAIN_EVERY == 0:
				send_retrain_message(model_id)
				batch_id += 1
			logger.info('observation number: {}. Prediction: {}'.format(messages_count,pred))



if __name__ == '__main__':
	dataprocessor_id = 0
	dataprocessor_fname = 'dataprocessor_{}_.p'.format(dataprocessor_id)
	dataprocessor = pickle.load(open(DATAPROCESSORS_PATH/dataprocessor_fname, 'rb'))

	messages_count = read_messages_count(MESSAGES_PATH, RETRAIN_EVERY)
	batch_id = messages_count % RETRAIN_EVERY

	model_id = batch_id % (EXTRA_MODELS_TO_KEEP + 1)
	model_fname = 'model_{}_.p'.format(model_id)
	model = reload_model(MODELS_PATH/model_fname)

	consumer = KafkaConsumer(bootstrap_servers=KAFKA_HOST)
	consumer.subscribe(TOPICS)

	start(model_id, messages_count, batch_id)
