# -*- coding: utf-8 -*-
import os
import sys
import urllib
import requests
import json
from flask import Flask, request, Response, make_response
from contextlib import closing
# Twilio Helper Library
from twilio.twiml.voice_response import VoiceResponse, Gather, Say
# AWS Python SDK
import boto3
import re
from flask import Flask
from flask import jsonify
from flask import url_for
from flask import request
from flask import make_response
import datetime

# Setup global variables
apiai_client_access_key = os.environ["APIAPI_CLIENT_ACCESS_KEY"]
aws_access_key_id = os.environ["AWS_ACCESS_KEY_ID"]
aws_secret_key = os.environ["AWS_SECRET_KEY"]
apiai_url = "https://api.api.ai/v1/query"
apiai_querystring = {"v": "20150910"}
registered_users = {"+914444461497": "Paul",
                   "+914444462805": "Peter"
}
# Adjust the hints for improved Speech to Text
hints = "1 one first, 2 two second, 3 three third, 4 four fourth, 5 five fifth, 6 six sixth, 7 seven seventh, 8 eight eighth,9 nine ninth, 10 ten tenth, account acount akount, january, february, march, april, may, june, july, august, september, october, november, december"

app = Flask(__name__)

@app.route('/start', methods=['GET','POST'])
def start():
    caller_phone_number = request.values.get('From')
    user_id = request.values.get('CallSid')
    polly_voiceid = request.values.get('polly_voiceid', "Joanna")
    twilio_asr_language = request.values.get('twilio_asr_language', "en-IN")
    apiai_language = request.values.get('apiai_language', "en")
    caller_name = registered_users.get(caller_phone_number, " ")
    hostname = request.url_root

    # Initialize API.AI Bot
    headers = {
        'authorization': "Bearer " + apiai_client_access_key,
        'content-type': "application/json"
    }
    payload = {'event': {'name':'abn_bank_welcome', 'data': {'user_name': caller_name}},
               'lang': apiai_language,
               'sessionId': user_id
    }
    response = requests.request("POST", url=apiai_url, data=json.dumps(payload), headers=headers, params=apiai_querystring)
    print(response.text)
    output = json.loads(response.text)
    output_text = output['result']['fulfillment']['speech']
    output_text = output_text.decode("utf-8")
    resp = VoiceResponse()
		
    # Prepare for next set of user Speech
    values = {"prior_text": output_text}
    qs = urllib.urlencode(values)
    action_url = "/process_speech?" + qs
    gather = Gather(input="speech", hints=hints, language=twilio_asr_language, timeout="3", action=action_url, method="POST")
	
    # TTS the bot response
    values = {"text": output_text,
              "polly_voiceid": polly_voiceid,
              "region": "us-east-1"
    }
    qs = urllib.urlencode(values)
    gather.play(hostname + 'polly_text2speech?' + qs)
    resp.append(gather)

    # If gather is missing (no speech), redirect to process speech again
    values = {"prior_text": output_text,
              "polly_voiceid": polly_voiceid,
              "twilio_asr_language": twilio_asr_language,
              "apiai_language": apiai_language,
              "SpeechResult": "",
              "Confidence": 0.0
    }
    qs = urllib.urlencode(values)
    action_url = "/process_speech?" + qs
    resp.redirect(action_url)
    print str(resp)
    return str(resp)

#####
##### Process Twilio ASR: Text to Intent analysis
#####
@app.route('/process_speech', methods=['GET', 'POST'])
def process_speech():
    user_id = request.values.get('CallSid')
    polly_voiceid = request.values.get('polly_voiceid', "Joanna")
    twilio_asr_language = request.values.get('twilio_asr_language', "en-IN")
    apiai_language = request.values.get('apiai_language', "en")
    prior_text = request.values.get('prior_text', "Prior text missing")
    prior_dialog_state = request.values.get('prior_dialog_state', "ElicitIntent")
    input_text = request.values.get("SpeechResult", "")
    confidence = float(request.values.get("Confidence", 0.0))
	hostname = request.url_root
	print "Twilio Speech to Text: " + input_text + " Confidence: " + str(confidence)
	actualvalue = re.findall(r'\b\d{3,16}\b', input_text)
	input_text = re.sub(r'\b\d{3,16}\b','1111111', input_text)
	print(input_text)
	sys.stdout.flush()
	
	resp = VoiceResponse()
	if (confidence > 0.5):
        # Step 1: Call Bot for intent analysis - API.AI Bot
        intent_name, output_text, dialog_state = apiai_text_to_intent(apiai_client_access_key, input_text, user_id, apiai_language)
        
        # Step 2: Construct TwiML
        if dialog_state in ['in-progress']:
            values = {"prior_text": output_text, "prior_dialog_state": dialog_state}
            qs2 = urllib.urlencode(values)
        	action_url = "/process_speech?" + qs2
        	gather = Gather(input="speech", hints=hints, language=twilio_asr_language, timeout="3", action=action_url,method="POST")
        	values = {"text": output_text,
                      "polly_voiceid": polly_voiceid,
                      "region": "us-east-1"
            }
            qs1 = urllib.urlencode(values)
            gather.play(hostname + 'polly_text2speech?' + qs1)
            resp.append(gather)
            
        # If gather is missing (no speech), redirect to process incomplete speech via the Bot
            values = {"prior_text": output_text,
                      "polly_voiceid": polly_voiceid,
                      "twilio_asr_language": twilio_asr_language,
                      "apiai_language": apiai_language,
                      "SpeechResult": "",
                      "Confidence": 0.0}
            
            qs3 = urllib.urlencode(values)
            action_url = "/process_speech?" + qs3
            resp.redirect(action_url)
        elif dialog_state in ['complete']:
            values = {"text": output_text,
                      "polly_voiceid": polly_voiceid,
                      "region": "us-east-1"
            }
            qs = urllib.urlencode(values)
            resp.play(hostname + 'polly_text2speech?' + qs)
            resp.hangup()
        elif dialog_state in ['Failed']:
            values = {"text": "I am sorry, there was an error.  Please call again!",
                    "polly_voiceid": polly_voiceid,
                    "region": "us-east-1"
            }
            qs = urllib.urlencode(values)
            resp.play(hostname + 'polly_text2speech?' + qs)
            resp.hangup()
    else:
        # We didn't get STT of higher confidence, replay the prior conversation
        output_text = prior_text
        dialog_state = prior_dialog_state
        values = {"prior_text": output_text,
                  "polly_voiceid": polly_voiceid,
                  "twilio_asr_language": twilio_asr_language,
                  "apiai_language": apiai_language,
                  "prior_dialog_state": dialog_state}
        qs2 = urllib.urlencode(values)
        action_url = "/process_speech?" + qs2
        gather = Gather(input="speech", hints=hints, language=twilio_asr_language, timeout="3", action=action_url, method="POST")
        values = {"text": output_text,
                  "polly_voiceid": polly_voiceid,
                  "region": "us-east-1"
                  }
        qs1 = urllib.urlencode(values)
        gather.play(hostname + 'polly_text2speech?' + qs1)
        resp.append(gather)

        values = {"prior_text": output_text,
                  "polly_voiceid": polly_voiceid,
                  "twilio_asr_language": twilio_asr_language,
                  "apiai_language": apiai_language,
                  "prior_dialog_state": dialog_state
                  }
        qs2 = urllib.urlencode(values)
        action_url = "/process_speech?" + qs2
        resp.redirect(action_url)
    print str(resp)
    return str(resp), actualvalue

#####
##### Google Api.ai - Text to Intent
#####
#@app.route('/apiai_text_to_intent', methods=['GET', 'POST'])
def apiai_text_to_intent(apiapi_client_access_key, input_text, user_id, language):
    headers = {
        'authorization': "Bearer " + apiapi_client_access_key,
        'content-type': "application/json"
    }
    payload = {'query': input_text,
               'lang': language,
               'sessionId': user_id
    }
    response = requests.request("POST", url=apiai_url, data=json.dumps(payload), headers=headers, params=apiai_querystring)
    output = json.loads(response.text)
    print json.dumps(output, indent=2)
    try:
        output_text = output['result']['fulfillment']['speech']
    except:
        output_text = ""
    try:
        intent_stage = output['result']['contexts']
    except:
        intent_stage = "unknown"

    if (output['result']['actionIncomplete']):
        dialog_state = 'in-progress'
    else:
        dialog_state = 'complete'

    return intent_stage, output_text, dialog_state

#####
##### API.API fulfillment webhook (You can enable this in API.AI console)
#####
@app.route('/webhook', methods=['POST'])
def webhook():
	req = request.get_json(silent=True, force=True)
	print 'Request:'
    print json.dumps(req, indent=4)
    res = processRequest(req)
    res = json.dumps(res, indent=4)
    # print(res)
    r = make_response(res)
    r.headers['Content-Type'] = 'application/json'
    return r

def processRequest(req):
	result = req.get('result')
    metadata = result.get('metadata')
    intentname = metadata.get('intentName')
    parameters = result.get('parameters')
    actionname = parameters.get('action')
    accounttype = parameters.get('type')
    #custname = parameters.get('customername')
	phoneNo = parameters.get('phonenumber')
	payeename = parameters.get('transcustomername')
	payeeaccounttype = parameters.get('transtype')
	payeeamount = parameters.get('amount')
	a, actualvalue = process_speech()
	#Get Balance Amount for account from account id
	if intentname == 'Account_Balance':
        Balance = getBalance(actualvalue, accounttype)
		speech = 'Your ' + accounttype + ' account balance is ' + Balance + ' dollars'
	else:
		speech = 'You will be receiving a call on this number shortly'
		return {'speech': speech,
                'displayText': speech,
                'source': 'apiai-account-sample'
        }
    return res

#Helper function for Balance
def getBalance(nickname, Accounttype):
    with open('details.json') as json_file:
	details = json.load(json_file)
    apiKey = os.environ.get('NESSIE_API_KEY')
    print apiKey
    if Accounttype == 'Savings':
        accountId = details[nickname]['Savings']
    elif Accounttype == 'Checking':
        accountId = details[nickname]['Checking']
    else:
        accountId = details[nickname]['Credit Card']
    url = 'http://api.reimaginebanking.com/accounts/{}?key={}'.format(accountId,apiKey)
    print url
    response = requests.get(url, headers={'content-type': 'application/json'})
    result = response.json()
    #print result
    accountbalance = result[u'balance']
    Balance = str(accountbalance)
    return Balance

#####
##### AWS Polly for Text to Speech
##### This function calls Polly and then streams out the in-memory media in mp3 format
#####
@app.route('/polly_text2speech', methods=['GET', 'POST'])
def polly_text2speech():
    text = request.args.get('text', "Hello! Invalid request. Please provide the TEXT value")
    voiceid = request.args.get('polly_voiceid', "Joanna")
    region = request.args.get('region', "us-east-1")
    # Create a client using the credentials and region
    polly = boto3.client("polly", aws_access_key_id = aws_access_key_id, aws_secret_access_key = aws_secret_key, region_name=region)
    # Request speech synthesis
    response = polly.synthesize_speech(Text=text, SampleRate="8000", OutputFormat="mp3", VoiceId=voiceid)

    # Access the audio stream from the response
    if "AudioStream" in response:
        # Note: Closing the stream is important as the service throttles on the
        # number of parallel connections. Here we are using contextlib.closing to
        # ensure the close method of the stream object will be called automatically
        # at the end of the with statement's scope.
        def generate():
            with closing(response["AudioStream"]) as dmp3:
                data = dmp3.read(1024)
                while data:
                    yield data
                    data = dmp3.read(1024)
                    return Response(generate(), mimetype="audio/mpeg")
    else:
        # The response didn't contain audio data, exit gracefully
        print("Could not stream audio")
        return "Error"

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug = True)
