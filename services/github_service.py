import os
import logging
import time
from datetime import datetime, timedelta
import pytz
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

        self.repositories = [
            "ethereum/pm",
            "ethereum/EIPs",
            "ethereum/execution-apis",
            "ethereum/execution-specs",
            "ethereum/consensus-specs"
        ]
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

    def _make_timezone_aware(self, dt):
        """Convert naive datetime to UTC timezone-aware datetime"""
        if dt.tzinfo is None:
            return pytz.UTC.localize(dt)
        return dt.astimezone(pytz.UTC)

    def _fetch_repository_content(self, repo_name, start_date, end_date):
        """Fetch content from a single repository"""
        content = []
        try:
            logger.info(f"Fetching content from {repo_name}")
            repo = self.github.get_repo(repo_name)

            # Get recent issues and pull requests with error handling
            for attempt in range(self.max_retries):
                try:
                    issues = repo.get_issues(state='all', since=start_date)
                    for issue in issues:
                        issue_date = self._make_timezone_aware(issue.created_at)
                        if start_date <= issue_date <= end_date:
                            content.append({
                                'type': 'issue',
                                'title': issue.title,
                                'url': issue.html_url,
                                'body': issue.body,
                                'created_at': issue_date.replace(tzinfo=None),
                                'repository': repo_name
                            })
                            logger.debug(f"Fetched issue from {repo_name}: {issue.title}")
                    break
                except RateLimitExceededException:
                    if attempt < self.max_retries - 1:
                        self._handle_rate_limit()
                    else:
                        logger.error(f"Failed to fetch issues from {repo_name} after {self.max_retries} attempts")
                        raise

            # Get recent commits with error handling
            for attempt in range(self.max_retries):
                try:
                    commits = repo.get_commits(since=start_date, until=end_date)
                    for commit in commits:
                        commit_date = self._make_timezone_aware(commit.commit.author.date)
                        if start_date <= commit_date <= end_date:
                            content.append({
                                'type': 'commit',
                                'title': commit.commit.message.split('\n')[0],  # First line of commit message
                                'url': commit.html_url,
                                'body': commit.commit.message,
                                'created_at': commit_date.replace(tzinfo=None),
                                'repository': repo_name
                            })
                            logger.debug(f"Fetched commit from {repo_name}: {commit.sha[:7]}")
                    break
                except RateLimitExceededException:
                    if attempt < self.max_retries - 1:
                        self._handle_rate_limit()
                    else:
                        logger.error(f"Failed to fetch commits from {repo_name} after {self.max_retries} attempts")
                        raise

            logger.info(f"Successfully fetched {len(content)} items from {repo_name}")
            return content

        except GithubException as e:
            logger.error(f"Error fetching content from {repo_name}: {str(e)}")
            return []

    def fetch_recent_content(self, start_date=None, end_date=None):
        """
        Fetch content from all Ethereum repositories for a specific date range.
        If no dates provided, defaults to the previous week.
        """
        if start_date is None:
            current_date = datetime.utcnow()
            end_date = current_date.replace(hour=0, minute=0, second=0, microsecond=0)
            start_date = end_date - timedelta(days=7)

        # Ensure dates are timezone-aware
        start_date = self._make_timezone_aware(start_date)
        end_date = self._make_timezone_aware(end_date)

        logger.info(f"Fetching content from {start_date} to {end_date}")
        all_content = []

        for repo_name in self.repositories:
            for attempt in range(self.max_retries):
                try:
                    logger.info(f"Fetching from {repo_name} (Attempt {attempt + 1}/{self.max_retries})")
                    content = self._fetch_repository_content(repo_name, start_date, end_date)
                    if content:  # Only extend if we got content
                        all_content.extend(content)
                        logger.info(f"Added {len(content)} items from {repo_name}")
                    else:
                        logger.warning(f"No content found in {repo_name} for the specified date range")
                    break
                except Exception as e:
                    logger.error(f"Error fetching from {repo_name} (Attempt {attempt + 1}/{self.max_retries}): {str(e)}")
                    if attempt < self.max_retries - 1:
                        sleep_time = self.retry_delay * (attempt + 1)
                        logger.info(f"Retrying in {sleep_time} seconds...")
                        time.sleep(sleep_time)
                    continue

        logger.info(f"Successfully fetched total of {len(all_content)} items from all repositories")
        logger.info("Content breakdown by repository:")
        repo_stats = {}
        for item in all_content:
            repo = item['repository']
            repo_stats[repo] = repo_stats.get(repo, 0) + 1
        for repo, count in repo_stats.items():
            logger.info(f"- {repo}: {count} items")

        return all_content