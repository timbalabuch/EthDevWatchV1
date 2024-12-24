import os
import logging
from datetime import datetime, timedelta
import pytz
import tweepy

logger = logging.getLogger(__name__)

class TwitterService:
    def __init__(self):
        try:
            # Initialize Twitter API client
            self.auth = tweepy.OAuth1UserHandler(
                os.environ['TWITTER_API_KEY'],
                os.environ['TWITTER_API_SECRET'],
                os.environ['TWITTER_ACCESS_TOKEN'],
                os.environ['TWITTER_ACCESS_TOKEN_SECRET']
            )
            self.api = tweepy.API(self.auth)
            self.verify_credentials()
            logger.info("TwitterService initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Twitter API client: {str(e)}")
            raise

    def verify_credentials(self):
        """Verify Twitter API credentials"""
        try:
            self.api.verify_credentials()
            logger.info("Twitter API credentials verified successfully")
        except Exception as e:
            logger.error(f"Failed to verify Twitter credentials: {str(e)}")
            raise

    def get_list_tweets(self, list_id, start_date=None, end_date=None, limit=5):
        """
        Fetch tweets from a specified list within a date range
        """
        if not list_id:
            logger.error("List ID is required")
            return []

        try:
            # If no dates specified, use the past week
            if not end_date:
                end_date = datetime.now(pytz.UTC)
            if not start_date:
                start_date = end_date - timedelta(days=7)

            logger.info(f"Fetching tweets from list {list_id} between {start_date} and {end_date}")
            tweets = []

            try:
                # Verify list exists and is accessible
                twitter_list = self.api.get_list(list_id=list_id)
                logger.info(f"Successfully accessed list: {twitter_list.name}")

                # Fetch tweets from the list
                for tweet in tweepy.Cursor(
                    self.api.list_timeline,
                    list_id=list_id,
                    include_rts=False,
                    tweet_mode="extended"
                ).items(100):  # Fetch more than needed to filter by date
                    try:
                        # Convert tweet created_at to UTC
                        tweet_date = tweet.created_at
                        if tweet_date.tzinfo is None:
                            tweet_date = pytz.UTC.localize(tweet_date)

                        logger.debug(f"Processing tweet {tweet.id_str} from {tweet_date}")

                        # Check if tweet is within the date range
                        if start_date <= tweet_date <= end_date:
                            tweets.append({
                                'id': tweet.id_str,
                                'text': tweet.full_text,
                                'author': tweet.user.screen_name,
                                'created_at': tweet_date,
                                'likes': tweet.favorite_count,
                                'retweets': tweet.retweet_count,
                                'url': f"https://twitter.com/{tweet.user.screen_name}/status/{tweet.id_str}"
                            })
                            logger.debug(f"Added tweet {tweet.id_str} to results")

                            if len(tweets) >= limit:
                                logger.info(f"Reached tweet limit of {limit}")
                                break

                    except Exception as e:
                        logger.error(f"Error processing individual tweet: {str(e)}")
                        continue

                logger.info(f"Found {len(tweets)} tweets within the date range")

            except (tweepy.errors.Unauthorized, tweepy.errors.Forbidden) as e:
                logger.error(f"Authentication or permission error: {str(e)}")
                return []
            except tweepy.errors.NotFound as e:
                logger.error(f"Twitter list not found: {str(e)}")
                return []
            except Exception as e:
                logger.error(f"Error fetching tweets: {str(e)}")
                return []

            # Sort tweets by engagement (likes + retweets)
            tweets.sort(key=lambda x: (x['likes'] + x['retweets']), reverse=True)

            final_tweets = tweets[:limit]
            logger.info(f"Returning {len(final_tweets)} tweets sorted by engagement")
            return final_tweets

        except Exception as e:
            logger.error(f"Error in get_list_tweets: {str(e)}")
            return []

    def format_tweets_html(self, tweets):
        """Format tweets as HTML for article display"""
        if not tweets:
            logger.info("No tweets to format")
            return ""

        try:
            logger.info(f"Formatting {len(tweets)} tweets as HTML")
            html = '<div class="top-tweets-section mt-4">\n'
            html += '    <h2 class="section-title">Top Community Tweets</h2>\n'
            html += '    <div class="tweet-list">\n'

            for tweet in tweets:
                try:
                    html += f'''        <div class="tweet-card mb-3">
                <div class="tweet-header">
                    <span class="tweet-author">@{tweet['author']}</span>
                    <a href="{tweet['url']}" target="_blank" class="tweet-link">
                        <i class="bi bi-twitter"></i>
                    </a>
                </div>
                <div class="tweet-content">
                    {tweet['text']}
                </div>
                <div class="tweet-stats">
                    <span class="likes"><i class="bi bi-heart"></i> {tweet['likes']}</span>
                    <span class="retweets"><i class="bi bi-repeat"></i> {tweet['retweets']}</span>
                </div>
            </div>
    '''
                except KeyError as e:
                    logger.error(f"Missing required field in tweet data: {str(e)}")
                    continue

            html += '    </div>\n</div>'
            logger.info("Successfully formatted tweets HTML")
            return html

        except Exception as e:
            logger.error(f"Error formatting tweets HTML: {str(e)}")
            return ""