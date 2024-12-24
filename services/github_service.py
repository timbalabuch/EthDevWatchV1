import os
import logging
import time
from datetime import datetime, timedelta
from github import Github
from github.GithubException import GithubException, RateLimitExceededException

logger = logging.getLogger(__name__)

class GitHubService:
    def __init__(self):
        self.github_token = os.environ.get('GITHUB_TOKEN')
        if not self.github_token:
            logger.warning("GitHub token not found, using unauthenticated client")
            self.github = Github()
        else:
            logger.info("Initializing GitHub client with authentication")
            self.github = Github(self.github_token)
        self.pm_repo = "ethereum/pm"
        self.max_retries = 3
        self.retry_delay = 5  # seconds

    def _handle_rate_limit(self):
        """Handle rate limit by waiting until reset"""
        rate_limit = self.github.get_rate_limit()
        reset_timestamp = rate_limit.core.reset.timestamp()
        sleep_time = int(reset_timestamp - time.time()) + 1
        if sleep_time > 0:
            logger.warning(f"Rate limit exceeded. Waiting {sleep_time} seconds for reset...")
            time.sleep(sleep_time)

    def fetch_recent_content(self, start_date=None, end_date=None):
        """
        Fetch content from Ethereum PM repository for a specific date range.
        If no dates provided, defaults to the previous week.
        """
        if start_date is None:
            # Get previous week's Monday to Sunday
            current_date = datetime.utcnow()
            end_date = current_date.replace(hour=0, minute=0, second=0, microsecond=0)
            start_date = end_date - timedelta(days=7)

        logger.info(f"Fetching content from {start_date} to {end_date}")

        for attempt in range(self.max_retries):
            try:
                logger.info(f"Fetching content from {self.pm_repo} (Attempt {attempt + 1}/{self.max_retries})")
                repo = self.github.get_repo(self.pm_repo)
                content = []

                # Get recent issues and pull requests
                try:
                    issues = repo.get_issues(state='all', since=start_date)
                    for issue in issues:
                        if start_date <= issue.created_at <= end_date:
                            content.append({
                                'type': 'issue',
                                'title': issue.title,
                                'url': issue.html_url,
                                'body': issue.body,
                                'created_at': issue.created_at.replace(tzinfo=None)
                            })
                            logger.debug(f"Fetched issue: {issue.title}")
                except RateLimitExceededException:
                    self._handle_rate_limit()
                    continue

                # Get recent commits
                try:
                    commits = repo.get_commits(since=start_date, until=end_date)
                    for commit in commits:
                        content.append({
                            'type': 'commit',
                            'title': commit.commit.message,
                            'url': commit.html_url,
                            'body': commit.commit.message,
                            'created_at': commit.commit.author.date.replace(tzinfo=None)
                        })
                        logger.debug(f"Fetched commit: {commit.sha[:7]}")
                except RateLimitExceededException:
                    self._handle_rate_limit()
                    continue

                logger.info(f"Successfully fetched {len(content)} items from GitHub")
                return content

            except GithubException as e:
                logger.error(f"GitHub API error (Attempt {attempt + 1}/{self.max_retries}): {str(e)}")
                if attempt < self.max_retries - 1:
                    sleep_time = self.retry_delay * (attempt + 1)
                    logger.info(f"Retrying in {sleep_time} seconds...")
                    time.sleep(sleep_time)
                continue

            except Exception as e:
                logger.error(f"Unexpected error fetching GitHub content: {str(e)}")
                if attempt < self.max_retries - 1:
                    sleep_time = self.retry_delay * (attempt + 1)
                    logger.info(f"Retrying in {sleep_time} seconds...")
                    time.sleep(sleep_time)
                continue

        logger.error("All retry attempts failed")
        return []