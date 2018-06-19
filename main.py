# -*- coding: utf-8 -*-
import os
import sys
import urllib
import requests
import json
from flask import Flask, request, Response, make_response, jsonify, url_for
from contextlib import closing
# Twilio Helper Library
from twilio.twiml.voice_response import VoiceResponse, Gather, Say
# AWS Python SDK
import boto3
import re
import datetime

# Declare global variables
apiai_client_access_key = os.environ["APIAPI_CLIENT_ACCESS_KEY"]
aws_access_key_id = os.environ["AWS_ACCESS_KEY_ID"]
aws_secret_key = os.environ["AWS_SECRET_KEY"]
apiKey = os.environ["NESSIE_API_KEY"]
apiai_url = "https://api.api.ai/v1/query"
apiai_querystring = {"v": "20150910"}
registered_users = {"+919840610434": "Vijay",
                   "+914444461324": "Vijay"
}

# Setup hints for better speech recognition
hints = "1,2,3,4,5,6,7,8,9,0, 1 one first, 2 two second, 3 three third, 4 four fourth, 5 five fifth, 6 six sixth, 7 seven seventh, 8 eight eighth,9 nine ninth, 10 ten tenth, account acount akount, january, february, march, april, may, june, july, august, september, october, november, december"

app = Flask(__name__)

@app.route('/start', methods=['GET','POST'])
def start():
    caller_phone_number = request.values.get('From')
    user_id = request.values.get('CallSid')
    polly_voiceid = request.values.get('polly_voiceid', 'Joanna')
    twilio_asr_language = request.values.get('twilio_asr_language', 'en-IN')
    apiai_language = request.values.get('apiai_language', 'en')
    caller_name = registered_users.get(caller_phone_number, ' ')
    hostname = request.url_root

    # Initialize Dialogflow agent
    headers = {'authorization': 'Bearer ' + apiai_client_access_key,
               'content-type': 'application/json'}
    payload = {'event': {'name': 'welcome',
               'data': {'user_name': caller_name}},
               'lang': apiai_language, 'sessionId': user_id}
    
    response = requests.request("POST", url=apiai_url, data=json.dumps(payload), headers=headers, params=apiai_querystring)
    print response.text
    output = json.loads(response.text)
    output_text = output['result']['fulfillment']['speech']
    output_text = output_text.decode('utf-8')
    resp = VoiceResponse()

    # Prepare for next set of user Speech
    values = {'prior_text': output_text}
    qs = urllib.urlencode(values)
    action_url = '/process_speech?' + qs
    gather = Gather(input="speech", hints=hints, language=twilio_asr_language, speechTimeout="auto", action=action_url, method="POST")
    
    # TTS dialogflow response
    values = {"text": output_text,
              "polly_voiceid": polly_voiceid,
              "region": "us-east-1"
             }
    qs = urllib.urlencode(values)
    print 'In start: before polly TTS'
    gather.play(hostname + 'polly_text2speech?' + qs)
    print 'In start: after polly TTS'
    resp.append(gather)

    # If gather is missing (no speech input), redirect to /process_speech again
    values = {'prior_text': output_text,
              "polly_voiceid": polly_voiceid,
              'twilio_asr_language': twilio_asr_language,
              'apiai_language': apiai_language,
              'SpeechResult': '',
              'Confidence': 0.0
             }
    qs = urllib.urlencode(values)
    action_url = '/process_speech?' + qs
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
    twilio_asr_language = request.values.get('twilio_asr_language', 'en-IN')
    apiai_language = request.values.get('apiai_language', 'en')
    prior_text = request.values.get('prior_text', 'Prior text missing')
    #prior_dialog_state = request.values.get('prior_dialog_state', 'ElicitIntent')
    input_text = request.values.get('SpeechResult', '')
    confidence = float(request.values.get('Confidence', 0.0))
    hostname = request.url_root
    print "Twilio Speech to Text: " + input_text + " Confidence: " + str(confidence)
    
    # Swapping the value if it has PII data
    if re.search(r'\b\d{1,16}\b', input_text):
        input_text = re.sub('(?<=\d) (?=\d)', '', input_text)
        input_text1 = swap(input_text)
        input_text = re.sub(r'\b\d{1,16}\b', input_text1, input_text)
        print "Changed input: " + input_text
    else:
        #input_text1 = input_text
        print "Unchanged input: " + input_text
    sys.stdout.flush()
    
    resp = VoiceResponse()
    if (confidence >= 0.0):

        # Step 1: Call Dialogflow for intent analysis
        intent_name, output_text, dialog_state = apiai_text_to_intent(apiai_client_access_key, input_text, user_id, apiai_language)

        # Step 2: Construct TwiML
        #if dialog_state in ['in-progress']:
        values = {'prior_text': output_text, 'prior_dialog_state': dialog_state}
        qs2 = urllib.urlencode(values)
        action_url = '/process_speech?' + qs2
        gather = Gather(input="speech", hints=hints, language=twilio_asr_language, speechTimeout="auto", action=action_url, method="POST")
        values = {"text": output_text, 
		  "polly_voiceid": polly_voiceid, 
		  "region": "us-east-1"
                     }
	qs1 = urllib.urlencode(values)
	print 'In-progress: Before polly tts'
	gather.play(hostname + 'polly_text2speech?' + qs1)
	print 'In progress: After polly tts'
	resp.append(gather)

        # If gather is missing (no speech input), redirect to process incomplete speech via Dialogflow
        values = {'prior_text': output_text, 
		  "polly_voiceid": polly_voiceid, 
		  'twilio_asr_language': twilio_asr_language, 
		  'apiai_language': apiai_language, 
		  'SpeechResult': '', 
		  'Confidence': 0.0
		 }
        qs3 = urllib.urlencode(values)
        action_url = '/process_speech?' + qs3
        resp.redirect(action_url)
	'''	
        # If intent is fulfilled, read the fulfillment speech    
        elif dialog_state in ['complete']:
	    print 'Output_text is: ' + output_text	
	    values = {"text": output_text, "polly_voiceid": polly_voiceid, "region": "us-east-1"}
	    qs = urllib.urlencode(values)
            print 'in complete: before polly tts'
	    resp.play(hostname + 'polly_text2speech?' + qs)
	    dialog_state = 'in-progress'
	    
	    resp.append(gather)
	    resp.hangup()
		
	    	
	    values = {'prior_text': output_text, 'prior_dialog_state': dialog_state}
            qs4 = urllib.urlencode(values)
            action_url = '/process_speech?' + qs4
            gather = Gather(input="speech", hints=hints, language=twilio_asr_language, speechTimeout="auto", action=action_url, method="POST")
            values = {"text": output_text, 
                      "polly_voiceid": polly_voiceid, 
                      "region": "us-east-1"
                     }
            qs5 = urllib.urlencode(values)
            print 'In-progress: Before polly tts'
            gather.play(hostname + 'polly_text2speech?' + qs5)
            print 'In progress: After polly tts'
            resp.append(gather)

            # If gather is missing (no speech input), redirect to process incomplete speech via Dialogflow
            values = {'prior_text': output_text, 
                      "polly_voiceid": polly_voiceid, 
                      'twilio_asr_language': twilio_asr_language, 
                      'apiai_language': apiai_language, 
                      'SpeechResult': '', 
                      'Confidence': 0.0
                     }
            qs8 = urllib.urlencode(values)
            action_url = '/process_speech?' + qs8
            resp.redirect(action_url)
	    
        elif dialog_state in ['Failed']:
            values = {"text": "I am sorry, there was an error.  Please call again!", 
                      "polly_voiceid": polly_voiceid, 
                      "region": "us-east-1"
                      }
            qs = urllib.urlencode(values)
            print 'In failed: Before polly tts'
            resp.play(hostname + 'polly_text2speech?' + qs)
            print 'In failed: After polly tts'
            resp.hangup()
	'''	
    else:
        # When confidence of speech recogniton is not enough, replay the prior conversation
        output_text = prior_text
        dialog_state = prior_dialog_state
        values = {"prior_text": output_text,
                  "polly_voiceid": polly_voiceid,
                  "twilio_asr_language": twilio_asr_language,
                  "apiai_language": apiai_language,
                  "prior_dialog_state": dialog_state}
        qs2 = urllib.urlencode(values)
        action_url = "/process_speech?" + qs2
        gather = Gather(input="speech", hints=hints, language=twilio_asr_language, speechTimeout="auto", action=action_url, method="POST")
        values = {"text": output_text,
                  "polly_voiceid": polly_voiceid,
                  "region": "us-east-1"
                  }
        qs1 = urllib.urlencode(values)
        print 'Before calling polly tts'
        gather.play(hostname + 'polly_text2speech?' + qs1)
        print 'After polly tts read'
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
    return str(resp)

#####
##### Google Dialogflow - Intent identification from text
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
    '''
    if (output['result']['actionIncomplete']):
        dialog_state = 'in-progress'
    else:
        dialog_state = 'in-progress'
    '''
    return intent_stage, output_text #, dialog_state

#####
##### Reversing Values
#####
def swap(text):
    actual = re.findall(r'\b\d{1,16}\b', text)
    actvalue = actual[0]
    text = actvalue[::-1]
    print "Swap function result: " + text
    return text

#####
##### Dialogflow fulfillment webhook
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
    accno = parameters.get('accnum')
    print "Sent account Number is: " + str(accno)
    payeeacc = parameters.get('transaccnum')
    payeeaccounttype = parameters.get('transtype')
    transamount = parameters.get('amount')
    phoneNo = parameters.get('phonenumber')

    # Get Balance Amount for account from account id
    if intentname == 'Account_Balance':
        accnumb = str(accno)
        accountnumber = swap(accnumb)
        print 'Account number:' + accountnumber
        Balance = getBalance(accountnumber, accounttype)
        speech = 'Your ' + accounttype + ' account balance is ' \
            + Balance + ' dollars. Is there anything else I can help you with today? You can check for your last purchase or last transfer or just hangup.'
        
    # Get Last transfer for account from account id
    elif intentname == 'Last_transfer':
        accnumb = str(accno)
        accountnumber = swap(accnumb)
        print 'Account number:' + accountnumber
        lasttransfer = getLasttransfer(accountnumber, accounttype)
        Amount = lasttransfer[0][u'amount']
        Transferamount = str(Amount)
        date = lasttransfer[0][u'transaction_date']
        Transferdate = str(date)
        speech = 'The last transfer you made was for ' + Transferamount \
            + ' dollars on ' + Transferdate + '.Is there anything else I can help you with today? You can check for your balance or last transfer or just hangup.'
        
    # Get Last purchase for account from account id    
    elif intentname == 'Last_purchase':
        accnumb = str(accno)
        accountnumber = swap(accnumb)
        print 'Account number:' + accountnumber
        lastpurchase = getLastpurchase(accountnumber, accounttype)
        Amount = lastpurchase[0][u'amount']
        Purchaseamount = str(Amount)
        date = lastpurchase[0][u'purchase_date']
        Purchasedate = str(date)
        speech = 'The last purchase you made was for ' + Purchaseamount \
            + ' dollars on ' + Purchasedate + '.Is there anything else I can help you with today? You can check for your balance or last purchase or just hangup.'
   
    # Transfer funds through account id
    elif intentname == 'Transfer_funds':
        accnumb = str(accno)
        accountnumber = swap(accnumb)
        print 'Account number:' + accountnumber
        payeeaccnumb = str(payeeacc)
        payeeaccountnumber = swap(payeeaccnumb)
        print 'Payee Account number:' + payeeaccountnumber
        xferamount = str(transamount)
        transferamount = swap(xferamount)
        print 'Transfer amount:' + transferamount
        result = createTransfer(accountnumber, accounttype, payeeaccountnumber,
                                payeeaccounttype, transferamount)
        responsecode = result[u'code']
        transId = result[u'objectCreated'][u'_id']
        if responsecode == 201:
            speech = \
                'Your transfer request is successful. Your transaction id is ' \
                + transId
        else:
            speech = 'Your transfer is not successful'
    else:
        speech = \
            'I am sorry. We are experiencing some technical difficulty. Please call again later'

    return {'speech': speech, 'displayText': speech,
            'source': 'apiai-account-sample'}  # "data": data, # "contextOut": [],
    return res
    
#Helper function for Balance
def getBalance(accountnumber, accounttype):
    with open('details.json') as json_file:
        details = json.load(json_file)
        print apiKey, accountnumber
        accountId = details[accountnumber][accounttype]
        print accountId
        url = \
            'http://api.reimaginebanking.com/accounts/{}?key={}'.format(accountId,
                apiKey)
        print url
        response = requests.get(url,
                                headers={'content-type': 'application/json'
                                })
        result = response.json()
        accountbalance = result[u'balance']
        Balance = str(accountbalance)
        return Balance

#Helper function for Last Transfer
def getLasttransfer(accountnumber, accounttype):
    with open('details.json') as json_file:
        details = json.load(json_file)
        print apiKey, accountnumber
        accountId = details[accountnumber][accounttype]
        print accountId
        url = \
            'http://api.reimaginebanking.com/accounts/{}/transfers?type=payer&key={}'.format(accountId,
                apiKey)
        response = requests.get(url,
                                headers={'content-type': 'application/json'
                                })
        lasttransfer = response.json()
        return lasttransfer

#Helper function for Last Purchase
def getLastpurchase(accountnumber, accounttype):
    with open('details.json') as json_file:
        details = json.load(json_file)
        print apiKey, accountnumber
        accountId = details[accountnumber][accounttype]
        print accountId
        url = \
            'http://api.reimaginebanking.com/accounts/{}/purchases?key={}'.format(accountId,
                apiKey)
        response = requests.get(url,
                                headers={'content-type': 'application/json'
                                })
        lastpurchase = response.json()
        return lastpurchase
    
#Helper function for Transfer funds
def createTransfer(accountnumber, accounttype, payeeaccountnumber, payeeaccounttype, transferamount):
    print 'i am here'
    with open('details.json') as json_file:
        details = json.load(json_file)
        dateObject = datetime.date.today()
        dateString = dateObject.strftime('%Y-%m-%d')
        payeraccountId = details[accountnumber][accounttype]
        payeeaccountId = details[payeeaccountnumber][payeeaccounttype]
        print payeeaccountId, payeraccountId
        url = \
            'http://api.reimaginebanking.com/accounts/{}/transfers?key={}'.format(payeraccountId,
                apiKey)
        payload = {
            'medium': 'balance',
            'payee_id': payeeaccountId,
            'amount': float(transferamount),
            'transaction_date': dateString,
            'description': 'Personal',
            }
        response = requests.post(url, data=json.dumps(payload),
                                 headers={'content-type': 'application/json'
                                 })
        result = response.json()
        print result
        return result

#####
##### AWS Polly for Text to Speech
##### This function calls Polly and then streams out the in-memory media in mp3 format
#####
@app.route('/polly_text2speech', methods=['GET', 'POST'])
def polly_text2speech():
    print 'Inside polly tts method'
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
            print 'inside polly tts generate method'
            with closing(response["AudioStream"]) as dmp3:
                data = dmp3.read(1024)
                while data:
                    yield data
                    data = dmp3.read(1024)
            print 'generate complete for polly tts'
        return Response(generate(), mimetype="audio/mpeg")
    else:
        # The response didn't contain audio data, exit gracefully
        print("Could not stream audio")
        return "Error"
    
if __name__ == '__main__':
    app.run(host='0.0.0.0', debug = True)
