import os
import logging
import time#, threading
import json
import datetime

from flask import Flask, url_for, request, render_template, redirect, flash
import tweepy

from friends import User
import model

app = Flask(__name__)


TIME_TO_WAIT = 900/180 # 15 minutes divided into 180 requests
NUM_RETRIES = 2
RATE_LIMITED_RESOURCES =[("statuses", "/statuses/user_timeline")]

# logging.basicConfig(filename='rate_limits.log',level=logging.DEBUG)


@app.route("/")
def index():
	return render_template("index.html")

@app.route("/display", methods=["POST"])
def display_friends():
	screen_name = request.json["screen_name"]
	print "SCREEN NAME FROM JSON: ", screen_name
	api = connect_to_API()

	print check_rate_limit(api)
	# print retrieve_remaining_requests(api)

	political_hashtags_dict = model.Hashtag.get_all_political_hashtags()

	user = User(api, central_user=screen_name, user_id=screen_name)
	timeline = user.get_timeline(user.USER_ID, user.MAX_NUM_TWEETS)
	# logging.info("Initial timeline request: \n", check_rate_limit(api))
	hashtag_count = user.count_hashtags(timeline)
	user.SCORE = user.score(hashtag_count, political_hashtags_dict)
	print "USER SCREEN NAME FROM USER OBJ: ", user.SCREEN_NAME
	print user.SCORE

	try:

		friends_ids = user.get_friends_ids(screen_name)

		friendlist = []

		for page in user.paginate_friends(friends_ids, 100):
			friends = process_friend_batch(user, page, api)
			friendlist.extend(friends)

		if len(friendlist) > user.MAX_NUM_FRIENDS:
			print "ORIGINAL LEN", len(friendlist)
			friendlist = get_top_influencers(friendlist, user.MAX_NUM_FRIENDS)
			print "NEW LEN", len(friendlist)

	except tweepy.TweepError as e:
		print "ERROR!!!!!", e

	friend_scores = list()

	try:
		for friend in friendlist:
			timeline = friend.get_timeline(friend.USER_ID, friend.MAX_NUM_TWEETS)
			# logging.info("Friend timeline request: \n", check_rate_limit(api))
			print check_rate_limit(api)
			# print retrieve_remaining_requests(api)

			hashtag_count = friend.count_hashtags(timeline)
			friend.SCORE = friend.score(hashtag_count, political_hashtags_dict)

			friend_scores.append({"screen_name": friend.SCREEN_NAME, "followers": friend.NUM_FOLLOWERS, "score": friend.SCORE})

			# friend_scores[friend.SCREEN_NAME] = {"followers": friend.NUM_FOLLOWERS, "score": friend.SCORE}

	except tweepy.TweepError as e:
		print "ERROR!!!!!", e
		# logging.warning("ERROR: \n", check_rate_limit(api))

	if len(friend_scores) > 0:
		print "FRIEND SCORES", friend_scores
		json_scores = json.dumps(friend_scores)
		# json_scores = [json.dumps(score_obj) for score_obj in friend_scores]
		return json_scores

	else:
		return redirect("/")#, add flash --> errormessage="Unable to get friends")

@app.route("/tweets")
def get_latest_tweets():
	pass
	screen_name = request.json["screen_name"]
	print "SCREEN NAME FROM JSON: ", screen_name
	api = connect_to_API()

	user = User(api, central_user=screen_name, user_id=screen_name)
	tweets = user.get_timeline(user.USER_ID, 5)
	json_tweets = json.dumps(tweets)

	return json_tweets

def process_friend_batch(user, page, api):
	"""
	Create User object for each friend in batch of 100 (based on pagination)
	"""
	batch = []
	friend_objs = user.lookup_friends(f_ids=page)
	for f in friend_objs:
		friend = User(api, central_user=user.CENTRAL_USER, user_id=f.id)
		friend.NUM_FOLLOWERS = f.followers_count
		friend.SCREEN_NAME = f.screen_name
		print friend.SCREEN_NAME, friend.NUM_FOLLOWERS
		# print "friend created"
		batch.append(friend)
	return batch

def get_top_influencers(friendlist, count):
	"""
	Get top influencers from user friends, as measured by # of followers.

	After requesting paginated friends, check "followers_count" attribute of
	each friend.

	Note:
	-----
	Run this function only if user has more than {count} friends.
	Currently, Twitter limits user timeline requests to 300
	(application auth) or 180 requests (user auth).

	Parameters:
	----------
	List of all friend objects.
	Number of top influencers to output.

	Output:
	-------
	List of {count} most influential friends

	"""

	sorted_by_influence = sorted(friendlist, key=lambda x: x.NUM_FOLLOWERS, reverse=True)
	friendlist = sorted_by_influence[:count]

	return friendlist

def check_rate_limit(api):
	"""
	Check Twitter API rate limit status for "statuses" (timeline) requests
	Print number of requests remaining per time period
	"""
	limits = api.rate_limit_status()
	stats = limits["resources"]["statuses"]
	for resource in stats.keys():
		if stats[resource]["remaining"] == 0:
			print "EXPIRED:", resource

		else:
			print resource, ":", stats[resource]["remaining"], "\n"

def connect_to_API():
	"""
	Create instance of tweepy API class with OAuth keys and tokens.
	"""
	# initialize tweepy api object with auth, OAuth
	TWITTER_API_KEY=os.environ.get('TWITTER_API_KEY')
	TWITTER_SECRET_KEY=os.environ.get('TWITTER_SECRET_KEY')
	TWITTER_ACCESS_TOKEN=os.environ.get('TWITTER_ACCESS_TOKEN')
	TWITTER_SECRET_TOKEN=os.environ.get('TWITTER_SECRET_TOKEN')

	auth = tweepy.OAuthHandler(TWITTER_API_KEY, TWITTER_SECRET_KEY, secure=True)
	auth.set_access_token(TWITTER_ACCESS_TOKEN, TWITTER_SECRET_TOKEN)
	api = tweepy.API(auth, cache=None)

	return api

if __name__ == "__main__":
	app.run(debug=True)
