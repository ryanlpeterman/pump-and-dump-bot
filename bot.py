import requests
import json
import time
import hmac
import hashlib
import twitter
import os
import pytesseract
import urllib, cStringIO

try:
    import Image
except ImportError:
    from PIL import Image
try:
    from urllib import urlencode
except ImportError:
    from urllib.parse import urlencode

from pprint import pprint
from datetime import datetime, timedelta

# Location of tesseract executable
pytesseract.pytesseract.tesseract_cmd = '/usr/local/bin/tesseract'

# Twitter API Keys
CONSUMER_KEY = os.environ.get('TWITTER_CONSUMER_KEY')
CONSUMER_SECRET = os.environ.get('TWITTER_CONSUMER_SECRET')
ACCESS_KEY = os.environ.get('TWITTER_ACCESS_KEY')
ACCESS_SECRET = os.environ.get('TWITTER_ACCESS_SECRET')

# Bittrex API Keys
BIT_KEY = os.environ.get('BITTREX_KEY')
BIT_SECRET = os.environ.get('BITTREX_SECRET')

# Constants
AVAILABLE_BTC = .01
PROFIT_MARGIN = 1.2
STOP_LOSS_PERCENT = .95

api = twitter.Api(consumer_key=CONSUMER_KEY,
                  consumer_secret=CONSUMER_SECRET,
                  access_token_key=ACCESS_KEY,
                  access_token_secret=ACCESS_SECRET)

def get_bittrex_markets():
    """ Returns all trading pairs on bittrex """
    r = requests.get('https://bittrex.com/api/v1.1/public/getmarkets')
    return r.json()['result']

def get_ticker_price(pairName):
    """ Returns current trading price of a pair on bittrex """
    r = requests.get('https://bittrex.com/api/v1.1/public/getticker?market=' + pairName)
    return r.json()['result']['Last']

def market_order(trade_type='sell',market=None, order_type='MARKET', quantity=None, rate=0, time_in_effect='FILL_OR_KILL',
              condition_type='NONE', target=0):
    """
    Enter a buy order into the book
    Endpoint v2.0: /key/market/tradebuy
    :param market (str): String literal for the market (ex: BTC-LTC)
    :param order_type (str): ORDERTYPE_LIMIT = 'LIMIT' or ORDERTYPE_MARKET = 'MARKET'
    :param quantity (float): The amount to purchase
    """ 
    options = {
            'marketname': market,
            'ordertype': order_type,
            'quantity': quantity,
            'rate': rate,
            'timeInEffect': time_in_effect,
            'conditiontype': condition_type,
            'target': target
    }

    request_url = 'https://bittrex.com/api/v2.0/key/market/trade{0}?'.format(trade_type)

    # unique always increasing integer
    nonce = str(int(time.time() * 1000))

    request_url = "{0}apikey={1}&nonce={2}&".format(request_url, BIT_KEY, nonce)
    request_url += urlencode(options)

    apisign = hmac.new(BIT_SECRET.encode(),
                   request_url.encode(),
                   hashlib.sha512).hexdigest()

    return requests.get(
            request_url,
            headers={"apisign": apisign}
        ).json()

def strategy(coin):
    """ 
    Current Strategy: Buy immediately for pump 
    Wait until price reaches target price or break even for stop loss
    """
    # get current price
    curr_price = get_ticker_price(coin['pairName'])

    # set constants
    QUANTITY = AVAILABLE_BTC/curr_price
    STOP_LOSS_PRICE = curr_price * STOP_LOSS_PERCENT
    EXIT_PRICE = curr_price * PROFIT_MARGIN

    # logging
    print("AVAILABLE BTC: " + str(AVAILABLE_BTC))
    print("STOP LOSS PRICE: " + str(STOP_LOSS_PRICE))
    print("EXIT PRICE: " + str(EXIT_PRICE) + '\n')
    print("BUYING: " + str(QUANTITY) + " " + coin['fullName'] + " at " + str(curr_price) + " BTC")

    market_order(trade_type='buy',
                market=coin['pairName'], 
                quantity=QUANTITY)

    # while price is in holding range
    while STOP_LOSS_PRICE < get_ticker_price(coin['pairName']) < EXIT_PRICE:
        time.sleep(1)

    # execute market sell
    curr_price = get_ticker_price(coin['pairName'])
    print("SELLING: " + str(AVAILABLE_BTC/last_price) + " " + coin['fullName'] + " at " + str(curr_price) + " BTC")

    market_order(trade_type='sell',
                 market=coin['pairName'],
                 quantity=QUANTITY)

def listen_tweet(user='officialmcafee'):
    """ Listens in on McAfee's twitter feed and returns next tweet text """
    for line in api.GetUserStream(withuser=user):
        # if image contained in tweet
        if line.get('entities') and line.get('entities').get('media'):
            image_url = line['entities']['media'][0]['media_url']
            file = cStringIO.StringIO(urllib.urlopen(image_url).read())
            img = Image.open(file)

            # return text in image tweet
            return pytesseract.image_to_string(img)

        # if regular tweet with text
        elif line.get('user') and line['user']['screen_name'] == user and line['text'][0] != '@':
            return line['text']

def preprocess(tweet_text):
    """ Given a string representing tweet text, returns tokenized list of lowercase strings """
    return tweet_text.lower().split()

if __name__ == '__main__':
    tokenized_tweet = preprocess(listen_tweet())

    # list of currencies available on bittrex as dictionaries
    currencies = []
    bittrex_markets = get_bittrex_markets()

    for market in bittrex_markets:
        # if the pair trades in btc
        if 'btc' in market['MarketName'].lower():
            currencies.append({
                'fullName':market['MarketCurrencyLong'], 
                'ticker':market['MarketCurrency'], 
                'pairName':market['MarketName']
                })
    
    # list of currencies mcafee mentioned
    to_buy = []
    for currency in currencies:
        if currency['fullName'].lower() in tokenized_tweet or currency['ticker'].lower() in tokenized_tweet:
            to_buy.append(currency)

    # if this isnt a decisive choice of what to buy
    if len(to_buy) != 1:
        print("ERROR: Currencies not available on Bittrex or more than one currency mentioned...")
        print("Currencies: " + ','.join(to_buy))
        exit(1)

    # begin pump and dump given coin
    strategy(to_buy[0])
    exit(0)
