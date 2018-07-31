# -*- coding: utf-8 -*-
import os
import sys
import urllib
import requests
import json
from flask import Flask, request, Response, make_response, jsonify, url_for
from contextlib import closing
# Twilio Helper Library
from twilio.twiml.voice_response import VoiceResponse, Gather, Say, Dial
# Google Text To Speech SDK
from google.oauth2 import service_account
from google.cloud import texttospeech_v1beta1 as texttospeech
# Dialogflow V2 SDK
import dialogflow
import re
import datetime

#####
##### Declare Global variables
#####
# Setting Google ID - Read env data
project_id = os.environ["DIALOGFLOW_PROJECT_ID"]
#Setting Google authorization credentials -  Read env data
credentials_dgf = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
call_id = "12345"
lang_code = 'en'

app = Flask(__name__)

# Receive call from Twilio with paramters
@app.route('/welcome', methods=['GET','POST'])
def welcome():
	#Setting Google Dialogflow Credentials and invoking SDK
	service_account_info = json.loads(credentials_dgf)
	credentials = service_account.Credentials.from_service_account_info(service_account_info)
	session_client = dialogflow.SessionsClient(credentials=credentials)
	session = session_client.session_path(project_id, call_id)
	event_input = dialogflow.types.EventInput(name='Welcome', language_code=lang_code)
	query_input = dialogflow.types.QueryInput(event=event_input)
	response = session_client.detect_intent(session=session, query_input=query_input)
	print response		
	output_text = response.query_result.fulfillment_text
	output_text = output_text.decode('utf-8')
	return output_text
	
#####
##### Process Twilio ASR: "Speech to Text" to Dialogflow Intent analysis
#####
@app.route('/process_speech', methods=['GET', 'POST'])
def process_speech():
	input_text = request.values.get('input_text', '')
	# Step 1: Call Dialogflow for intent analysis
	intent_name, output_text, product_name, emp_id = dialogflow_text_to_intent(project_id, input_text, call_id, lang_code)
	return intent_name, output_text, product_name, emp_id

#####
##### Google Dialogflow V2 API - Intent identification from text
#####
#@app.route('/dialogflow_text_to_intent', methods=['GET', 'POST'])
def dialogflow_text_to_intent(project_id, call_id, input_text, lang_code):

	#Generate Google Dialogflow Credentials
	service_account_info = json.loads(credentials_dgf)
	credentials = service_account.Credentials.from_service_account_info(service_account_info)

	session_client = dialogflow.SessionsClient(credentials=credentials)
	session = session_client.session_path(project_id, call_id)
	
	for text in input_text:
                text_input = dialogflow.types.TextInput(text=text, language_code=lang_code)
		query_input = dialogflow.types.QueryInput(text=text_input)
		response = session_client.detect_intent(session=session, query_input=query_input)
		output = json.loads(response.text)
		print output
		print json.dumps(output, indent=2)
	
		# Get values from Dialogflow
		try:
			intent_name = output['query_result']['intent']['display_name']
		except:
			intent_name= ""
		try:
			product_name = output['query_result']['parameters']['optus_product']
		except:
			product_name= ""
		try:
			emp_id = output['result']['parameters']['employee_id']
		except:
			emp_id= ""	
		try:
			output_text = output['query_result']['fulfillment_text']
		except:
			output_text = ""
    	
	return intent_name, output_text, product_name, emp_id
  
if __name__ == '__main__':
	app.run(host='0.0.0.0', debug = True)
