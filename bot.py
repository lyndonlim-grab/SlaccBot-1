import slack
import os
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, request, Response
from slackeventsapi import SlackEventAdapter
import string
from datetime import datetime, timedelta

#just to note where the env file can be found 
env_path = Path('.')/'.env' 
load_dotenv(dotenv_path=env_path)

app = Flask(__name__)

#slack event adapter will handle any slack events from the api.
#(signing secret from slack api, where events will be sent to, which web server events will be sent to)
slack_event_adapter = SlackEventAdapter(
    os.environ['SIGNING_SECRET'], '/slack/events', app)

#to note which variable to look at for the OAuth Token
client = slack.WebClient(token = os.environ['SLACK_TOKEN']) 

BOT_ID = client.api_call("auth.test")['user_id'] #gives us the ID of our own bot

#insert your own channel name. But must add this app to the channel first
client.chat_postMessage(channel='#slaccbot_test', text = 'Hello WERL. Type "Start" to start using Slaccbot.') 

message_counts = {}
welcome_messages = {}

BAD_WORDS = ['some_bad_word_examples', 'yikes']

SCHEDULED_MESSAGE = [
    {'text': 'First message', 'post_at': (datetime.now() + timedelta(seconds = 30, days=1)).timestamp(), 'channel': 'C024UR6C6UE' },
    {'text': 'Second message', 'post_at': (datetime.now() + timedelta(seconds = 50, days=1)).timestamp(), 'channel': 'C024UR6C6UE'}
]

class WelcomeMessage:
    START_TEXT = {
        'type': 'section',
        'text': {
            'type': 'mrkdwn',
            'text': (
                'Welcome to the Cheesecake Slaccbot Testing channel! \n\n'
                'In this channel, you can receive updates from our customer feedbacks.\n\n'
                '*Get started by telling us your preferences for customer feedback updates!*'
            )
        }
    }

    DIVIDER = {'type': 'divider'}

    def __init__(self, channel, user):
        self.channel = channel
        self.user = user
        self.timestamp = ''
        self.completed_1 = False
        self.completed_2 = False
        self.completed_3 = False

    def get_message(self):
        return {
            'ts': self.timestamp,
            'channel': self.channel,
            'blocks': [
                self.START_TEXT,
                self.DIVIDER,
                self._get_reaction_task()
            ]
        }

    #private method that should not be called outside of this class, denoted by _method
    #internal method to create the message being sent to the user
    def _get_reaction_task(self):
        checkmark1 = ':white_check_mark:' #emoji
        checkmark2 = ':white_check_mark:' #emoji
        checkmark3 = ':white_check_mark:' #emoji

        if not self.completed_1:
            checkmark1 = ':white_small_square:' #emoji

        if not self.completed_2:
            checkmark2 = ':white_small_square:' #emoji

        if not self.completed_3:
            checkmark3 = ':white_small_square:' #emoji

        text = f'\n {checkmark1} *Select the number of Feedbacks you would like to receive* (react to change) \n\n' \
            + f'{checkmark2} *Select the sentiment score you are interested in (1-5)* \n\n' \
            + f'{checkmark3} *Select the department you are interested in (eg.Food, Transport)*'

        return {'type': 'section',
            'text': {'type': 'mrkdwn', 'text': text}
        }

# #can try slack_event_adapter.on('team-join') for people who join the channel
# @slack_event_adapter.on('team-join')

def send_welcome_message(channel, user):
    # check if this welcome message has been to sent to this specific user in this specific channel
    if channel not in welcome_messages:
        welcome_messages[channel] = {}  

    if user in welcome_messages[channel]: #to prevent user from sending 'start' twice
        return

    welcome = WelcomeMessage(channel, user)
    message = welcome.get_message()
    response = client.chat_postMessage(**message) #unpack the dict to its key and value as stated in get_message()
    welcome.timestamp = response['ts']


    welcome_messages[channel][user] = welcome #append this welcome message class instance into the dict

# def schedule_messages(messages):
#     ids = []
#     for msg in messages:
#         response = client.chat_scheduleMessage(\
#             channel = msg['channel'], text = msg['text'], post_at = msg['post_at'])

#         id_ = response.get('id')
#         ids.append(id_)

#     return ids

# def delete_scheduled_messages():
    

def check_if_bad_words(message):
    msg = message.lower()
    msg = msg.translate(str.maketrans('', '', string.punctuation)) #removes all the punctuation that can mask a bad word

    return any(word in msg for word in BAD_WORDS)

#handles messages being sent in the channel
@slack_event_adapter.on('message')
def message(payload):
    #print(payload)
    event = payload.get('event', {})
    channel_id = event.get('channel')
    user_id = event.get('user')
    text = event.get('text')

    #check if message is from bot or actual user to prevent responding to our own messages
    if user_id != None and  BOT_ID != user_id:
        #to faciliate messagecount function
        if user_id in message_counts:
            message_counts[user_id] +=1
        else:
            message_counts[user_id] = 1

        #facilitate the start message
        if text.lower() == 'start':
            send_welcome_message(f'@{user_id}', user_id) # @{user_id} points to the user's DM with the slackbot
        
        elif check_if_bad_words(text):
            #uses time stamp to identify msg and reply to it
            ts = event.get('ts')
            client.chat_postMessage(channel=channel_id, thread_ts = ts, text = 'Bad Word has been detected!') 
            
        else:
            txt = 'Welcome to Cheesecake Slaccbot. Type "Start" to start using the service'
            client.chat_postMessage(channel=channel_id, text = txt)

    
        ## I guess we can add more incoming message handler. One for each of the task the user needs to complete.
        ## Each handler will update the data row before re-updating the external DB for user's preferences.

@slack_event_adapter.on('reaction_added')
def reaction(payload):
    #print(payload) #the payload sent by making a reaction is abit different, so the channel_id code is abit different
    event = payload.get('event', {})
    channel_id = event.get('item',{}).get('channel') #gets the channel id of the DM between the user and bot
    user_id = event.get('user')

    #if the welcome message has not been sent to this user's DM, no need to update the checkmark
    if f'@{user_id}' not in welcome_messages:
        return
    
    welcome = welcome_messages[f'@{user_id}'][user_id] #retrieve the initial welcomemessage sent to the user before any reaction
    welcome.completed_1 = True #update to show that task has been completed
    welcome.channel = channel_id #update the channel id of the welcome instance to be the convo between the bot and user
    message = welcome.get_message() #reinstantiate the new updated message
    updated_message = client.chat_update(**message) #reprint the updated message into the dm with the bot
    welcome.timestamp = updated_message['ts']

#handles the command /message-count
@app.route('/message-count', methods=['POST'])
def message_count():
    data = request.form #provides a dict tt shows what data was sent tgt with the Post request
    #print(data)
    user_id = data.get('user_id')
    user_name = data.get('user_name')
    channel_id = data.get('channel_id')

    count = message_counts.get(user_id, 0) #get the value if user_id exists in dict, else return 0

    # client.chat_postMessage(channel=channel_id, text = 'command received') 
    client.chat_postMessage(channel=channel_id, \
        text = f"Command received. Number of message sent by {user_name}: {count}") 

    return Response(), 200



if __name__ == "__main__":
    # schedule_messages(SCHEDULED_MESSAGE)
    app.run(debug=True)
    # app.run(debug=True, port = someInteger) if want to state another port other than 5000

