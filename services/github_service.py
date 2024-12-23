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

    def fetch_recent_content(self):
        """Fetch content from Ethereum PM repository from the past week with retry logic"""
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Fetching recent content from {self.pm_repo} (Attempt {attempt + 1}/{self.max_retries})")
                repo = self.github.get_repo(self.pm_repo)
                one_week_ago = datetime.utcnow() - timedelta(days=7)

                # Get recent issues and pull requests
                issues = repo.get_issues(state='all', since=one_week_ago)
                content = []

                # Fetch issues with retry logic
                try:
                    for issue in issues:
                        content.append({
                            'type': 'issue',
                            'title': issue.title,
                            'url': issue.html_url,
                            'body': issue.body,
                            'created_at': issue.created_at
                        })
                        logger.debug(f"Fetched issue: {issue.title}")
                except RateLimitExceededException:
                    self._handle_rate_limit()
                    continue

                # Get recent commits with retry logic
                try:
                    commits = repo.get_commits(since=one_week_ago)
                    for commit in commits:
                        content.append({
                            'type': 'commit',
                            'title': commit.commit.message,
                            'url': commit.html_url,
                            'body': commit.commit.message,
                            'created_at': commit.commit.author.date
                        })
                        logger.debug(f"Fetched commit: {commit.sha[:7]}")
                except RateLimitExceededException:
                    self._handle_rate_limit()
                    continue

                logger.info(f"Successfully fetched {len(content)} items from GitHub")
                return content

            except GithubException as e:
                logger.error(f"GitHub API error (Attempt {attempt + 1}/{self.max_retries}): {str(e)}")
                if e.status == 304:
                    logger.warning("Received 304 error - clearing internal cache and retrying...")
                    # Force a fresh request by recreating the client
                    self.github = Github(self.github_token)
                elif e.status == 401:
                    logger.error("Authentication failed - check GitHub token")
                    break  # Don't retry auth failures
                elif e.status == 403:
                    if "rate limit exceeded" in str(e).lower():
                        self._handle_rate_limit()
                    else:
                        logger.error("Permission denied")
                        break

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