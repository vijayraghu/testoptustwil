# -*- coding: utf-8 -*-
import os
import sys
import urllib
import requests
import json
from google.protobuf.json_format import MessageToJson
import re
import datetime
from flask import Flask, request, Response, make_response, jsonify, url_for
from contextlib import closing
# Twilio Helper Library
from twilio.twiml.voice_response import VoiceResponse, Gather, Say, Dial
# Google Text To Speech SDK
from google.oauth2 import service_account
from google.cloud import texttospeech_v1beta1 as texttospeech
# Dialogflow V2 SDK
import dialogflow


#####
##### Declare Global variables
#####
# Setting Google ID - Read env data
project_id = os.environ["DIALOGFLOW_PROJECT_ID"]
#Setting Google authorization credentials -  Read env data
credentials_dgf = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
call_id = "12345"
lang_code = 'en'
emp_id = "1043456"

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
	print output_text
	return output_text
	
#####
##### Process Twilio ASR: "Speech to Text" to Dialogflow Intent analysis
#####
@app.route('/process_speech', methods=['GET', 'POST'])
def process_speech():
	input_text = request.values.get('input_text', '')
	print input_text
	# Step 1: Call Dialogflow for intent analysis
	intent_name, output_text, optus_product = dialogflow_text_to_intent(project_id, call_id, input_text, lang_code)
	print intent_name, output_text, optus_product
	return output_text

#####
##### Google Dialogflow V2 API - Intent identification from text
#####
#@app.route('/dialogflow_text_to_intent', methods=['GET', 'POST'])
def dialogflow_text_to_intent(project_id, call_id, input_text, lang_code):
	print project_id, call_id, input_text, lang_code
	#Setting Google Dialogflow Credentials and invoking SDK
	service_account_info = json.loads(credentials_dgf)
	credentials = service_account.Credentials.from_service_account_info(service_account_info)
	session_client = dialogflow.SessionsClient(credentials=credentials)
	session = session_client.session_path(project_id, call_id)
	if input_text:
		text_input = dialogflow.types.TextInput(text=input_text, language_code=lang_code)
		query_input = dialogflow.types.QueryInput(text=text_input)
		response = session_client.detect_intent(session=session, query_input=query_input)
		print response
		paramvalues = MessageToJson(response.query_result.parameters)
		param_values = json.loads(paramvalues)
		print param_values
		print response.query_result.fulfillment_text.encode('utf-8')
		
		# Return properties from Dialogflow
		try:
			intent_name = response.query_result.intent.display_name
		except:
			intent_name = ""
		try:
			output_text = response.query_result.fulfillment_text
			output_text = output_text.encode('utf-8')
			print 'output: ' + output_text
		except:
			output_text = ""
		try:	
			optus_product = param_values["optus_product"]
		except:
			optus_product = ""
		try:
			emp_id = param_values["employee_id"]
		except:
			emp_id = ""

	return intent_name, output_text, optus_product

#####
##### Dialogflow fulfillment webhook
#####
@app.route('/webhook', methods=['POST'])
# Receive the JSON request from Dialogflow
def webhook():
	req = request.get_json(silent=True, force=True)
	print 'Request:'
	print json.dumps(req, indent=4)
	res = processRequest(req)
	res = json.dumps(res, indent=4)
	r = make_response(res)
	r.headers['Content-Type'] = 'application/json'
	return r

# Get details from JSON 
def processRequest(req):
	result = req.get('queryResult')
	metadata = result.get('intent')
	intentname = metadata.get('displayName')
	parameters = result.get('parameters')
	actionname = parameters.get('action')
	emp_id = parameters.get('employee_id')
	product_name = parameters.get('optus_product')
	
	# Handle Default Fallback Intent
	if intentname == 'Default Fallback Intent':
		print 'Intent :' + intentname
		context = result.get('outputContexts')
		if "parameters" in context[0]:
			con_emp_id = context[0]['parameters']['employee_id.original']
			print con_emp_id
			if str(con_emp_id) != '':
				print 'I am here'
				fulfillmentText = 'I not sure I quite understand. Apologies. I’m new here at Optus and still in training and learning about all our product lines, maybe if you could tell me the general reason for your call today like Billing or Sales or perhaps it’s technical. If you are not sure, please say exit' 
			else:
				fulfillmentText = 'I not sure I quite understand. Apologies. If you could just tell me your employee number speaking every digit individually, i can help you. If you dont have an employee number, thats fine. Just say you dont have it or say exit.'
		else:
			fulfillmentText = 'I not sure I quite understand. Apologies. If you could just tell me your employee number speaking every digit individually, i can help you. If you dont have an employee number, thats fine. Just say you dont have it or say exit.'
	
	# Process employee number
	if intentname == 'get_employee_number_cartwright':
		print 'Intent :' + intentname
		#Validate employee number
		if (str(int(emp_id))[:2]) != '10':
			fulfillmentText = 'Hmmm! That does not seem to be a valid employee number. Care for me is for internal employees only. Would you like me to transfer you to one of my colleagues in the General Customer Service Team that can help you with your inquiry today.'
		else:
			employee_name = get_employee_name(emp_id)
			fulfillmentText = 'Thanks ' + employee_name + ' for providing your employee number. Now how can we help you today?'
			
	# Process employee number again
	if intentname == 'get_employee_number_cartwright-again':
		if (str(int(emp_id))[:2]) != '10':
			fulfillmentText = 'Sorry that still don’t not check out, perhaps you should chat with your manager. Would you like me to transfer you to one of my colleagues in the General Customer Service Team that can help you with your inquiry today.'
		else:
			employee_name = get_employee_name(emp_id)
			fulfillmentText = 'Thanks ' + employee_name + ' for providing your employee number. Now how can we help you today?'
			
	# Transfer to General customer care when user says ok for transfer post unsuccessful employee id check
	if intentname == 'get_employee_number_cartwright-transfer':
		fulfillmentText = 'My colleague in the General Customer Service Team will help you with your inquiry today.'

    	# Transfer for Billing_services
    	elif intentname == 'billing_services_cartwright':
		if (str(int(emp_id))[:2]) != '10':
			fulfillmentText = 'Hmmm! That does not seem to be a valid employee number. Let me transfer you to one of my colleagues in the General Customer Service Team that can help you with your inquiry today.'
		else:
			fulfillmentText = 'Ok. Let me transfer you to one of my colleagues that can help you with your Billing inquiry'
	
    	# Transfer for Sales_services   
    	elif intentname == 'sales_services_cartwright':
		if (str(int(emp_id))[:2]) != '10':
			fulfillmentText = 'Hmmm! That does not seem to be a valid employee number. Let me transfer you to one of my colleagues in the General Customer Service Team that can help you with your inquiry today.'
		else:
			fulfillmentText = 'Ok. Let me transfer you to one of my colleagues that can help you with your Sales inquiry'
	
    	# Transfer for Tech_services
    	elif intentname == 'tech_services_cartwright':
		if (str(int(emp_id))[:2]) != '10':
			fulfillmentText = 'Hmmm! That does not seem to be a valid employee number. Let me transfer you to one of my colleagues in the General Customer Service Team that can help you with your inquiry today.'
		else:
			fulfillmentText = 'Ok. Let me transfer you to one of my colleagues that can help you with your technical inquiry'
			
    	# Transfer to General services if employee number is not provided
    	elif intentname == 'no_employee_number_cartwright':
		fulfillmentText = 'Let me transfer you to one of my colleagues in the General Customer Service Team that can help you with your inquiry today.'
		
	# Catch all error/exception scenarios and transfer to General services
	#else:
		#print 'I am here. please check'
		#fulfillmentText = 'Let me transfer you to one of my colleagues in the General Customer Service Team that can help you with your inquiry today.'
	
	return {'fulfillmentText': fulfillmentText, 'source': 'careformev2'}
	
	return res
	
#####
##### Helper function for employee name
#####
def get_employee_name(emp_id):
	print 'Inside Get employee name'
	print emp_id
	if str(int(emp_id)) == '1048350':
		employee_name = 'Chris'
	elif str(int(emp_id)) == '1048550':
		employee_name = 'Mick'
	elif str(int(emp_id)) == '1048560':
		employee_name = 'Josh'
	elif str(int(emp_id)) == '1058670':
		employee_name = 'Paul'
	elif str(int(emp_id)) == '1088430':
		employee_name = 'Cameron'
	else:
		employee_name = ''
		
	return employee_name

  
if __name__ == '__main__':
	app.run(host='0.0.0.0', debug = True)
