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

# Setup global variables
apiai_client_access_key = os.environ["APIAPI_CLIENT_ACCESS_KEY"]
aws_access_key_id = os.environ["AWS_ACCESS_KEY_ID"]
aws_secret_key = os.environ["AWS_SECRET_KEY"]
apiKey = os.environ["NESSIE_API_KEY"]
apiai_url = "https://api.api.ai/v1/query"
apiai_querystring = {"v": "20150910"}
registered_users = {"+919840610434": "Vijay",
                   "+914444461324": "Vijay"
}
# Adjust the hints for improved Speech to Text
hints = "1,2,3,4,5,6,7,8,9,0, 1 one first, 2 two second, 3 three third, 4 four fourth, 5 five fifth, 6 six sixth, 7 seven seventh, 8 eight eighth,9 nine ninth, 10 ten tenth, account acount akount, january, february, march, april, may, june, july, august, september, october, november, december"

app = Flask(__name__)

@app.route('/start', methods=['GET','POST'])
def start():
    caller_phone_number = request.values.get('From')
    user_id = request.values.get('CallSid')

    # polly_voiceid = request.values.get('polly_voiceid', "Joanna")

    twilio_asr_language = request.values.get('twilio_asr_language',
            'en-IN')
    apiai_language = request.values.get('apiai_language', 'en')
    caller_name = registered_users.get(caller_phone_number, ' ')
    hostname = request.url_root

    # Initialize API.AI Bot

    headers = {'authorization': 'Bearer ' + apiai_client_access_key,
               'content-type': 'application/json'}
    payload = {'event': {'name': 'abn_bank_welcome',
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
    gather = Gather(input="speech", hints=hints, language=twilio_asr_language, timeout="3", action=action_url, method="POST")

    # TTS the bot response

    gather.say(output_text, voice='alice', language='en-IN')
    resp.append(gather)

    # If gather is missing (no speech), redirect to process speech again

    values = {'prior_text': output_text,
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
    twilio_asr_language = request.values.get('twilio_asr_language', 'en-IN')
    apiai_language = request.values.get('apiai_language', 'en')
    prior_text = request.values.get('prior_text', 'Prior text missing')
    prior_dialog_state = request.values.get('prior_dialog_state', 'ElicitIntent')
    input_text = request.values.get('SpeechResult', '')
    confidence = float(request.values.get('Confidence', 0.0))
    hostname = request.url_root
    print "Twilio Speech to Text: " + input_text + " Confidence: " + str(confidence)
    
    # Swapping the value if it has PII data
    if re.search(r'\b\d{3,16}\b', input_text):
        input_text = re.sub('(?<=\d) (?=\d)', '', input_text)
        input_text1 = swap(input_text)
        input_text1 = re.sub(r'\b\d{3,16}\b', revact, input_text1)
        print input_text1
    else:
        input_text1 = input_text
        print input_text1
    sys.stdout.flush()
    resp = VoiceResponse()
    if (confidence >= 0.0):

        # Step 1: Call Bot for intent analysis - API.AI Bot
        intent_name, output_text, dialog_state = apiai_text_to_intent(apiai_client_access_key, input_text1, user_id, apiai_language)

        # Step 2: Construct TwiML
        if dialog_state in ['in-progress']:
            values = {'prior_text': output_text, 'prior_dialog_state': dialog_state}
            qs2 = urllib.urlencode(values)
            action_url = '/process_speech?' + qs2
            gather = Gather(input="speech", hints=hints, language=twilio_asr_language, timeout="3", action=action_url, method="POST")
            gather.say(output_text, voice='alice', language='en-IN')
            resp.append(gather)

            # If gather is missing (no speech), redirect to process incomplete speech via the Bot
            values = {'prior_text': output_text, 
                      'twilio_asr_language': twilio_asr_language, 
                      'apiai_language': apiai_language, 
                      'SpeechResult': '', 
                      'Confidence': 0.0
                     }
            qs3 = urllib.urlencode(values)
            action_url = '/process_speech?' + qs3
            resp.redirect(action_url)
        elif dialog_state in ['complete']:
            resp.say(output_text, voice='alice', language='en-IN')
            resp.hangup()
        elif dialog_state in ['Failed']:
            resp.say('I am sorry, there was an error.  Please call again!', voice='alice', language='en-IN')
            resp.hangup()
    else:

        # We didn't get STT of higher confidence, replay the prior conversation
        output_text = prior_text
        dialog_state = prior_dialog_state
        values = {'prior_text': output_text, 
                  'twilio_asr_language': twilio_asr_language, 
                  'apiai_language': apiai_language, 
                  'prior_dialog_state': dialog_state
                 }
        qs2 = urllib.urlencode(values)
        action_url = '/process_speech?' + qs2
        gather = Gather(input="speech", hints=hints, language=twilio_asr_language, timeout="3", action=action_url, method="POST")
        gather.say(output_text, voice='alice', language='en-IN')
        resp.append(gather)
        
        values = {'prior_text': output_text, 
                  'twilio_asr_language': twilio_asr_language, 
                  'apiai_language': apiai_language, 
                  'prior_dialog_state': dialog_state
                 }
        qs2 = urllib.urlencode(values)
        action_url = '/process_speech?' + qs2
        resp.redirect(action_url)
        print 'Resp:' + str(resp)
     return str(resp)

#####
##### Google Api.ai - Text to Intent
#####
#@app.route('/apiai_text_to_intent', methods=['GET', 'POST'])
def apiai_text_to_intent(apiapi_client_access_key, input_text1, user_id, language):
    headers = {
        'authorization': "Bearer " + apiapi_client_access_key,
        'content-type': "application/json"
    }
    payload = {'query': input_text1,
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
##### Reversing Function
#####
def swap(text):
    actual = re.findall(r'\b\d{1,16}\b', text)
    actvalue = actual[0]
    revact = actvalue[::-1]
    print revact
    return revact

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
    accno = parameters.get('accnum')
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
            + Balance + ' dollars'
        
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
            + ' dollars on ' + Transferdate
        
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
            + ' dollars on ' + Purchasedate
   
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
def getBalance(nickname, Accounttype):
    with open('details.json') as json_file:
        details = json.load(json_file)
        print apiKey, nickname
        accountId = details['Vijay'][Accounttype]
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
def getLasttransfer(nickname, Accounttype):
    with open('details.json') as json_file:
        details = json.load(json_file)
        print apiKey, nickname
        accountId = details['Vijay'][Accounttype]
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
def getLastpurchase(nickname, Accounttype):
    with open('details.json') as json_file:
        details = json.load(json_file)
        print apiKey, nickname
        accountId = details['Vijay'][Accounttype]
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
def createTransfer(
    name,
    Payeraccounttype,
    payee,
    Payeeaccounttype,
    transferamount,
    ):

    print 'i am here'
    with open('details.json') as json_file:
        details = json.load(json_file)
        dateObject = datetime.date.today()
        dateString = dateObject.strftime('%Y-%m-%d')
        payeraccountId = details['Vijay'][Payeraccounttype]
        payeeaccountId = details['Sriram'][Payeeaccounttype]
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug = True)
