import os
import logging
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import pytz
from github import Github
from github.GithubException import GithubException, RateLimitExceededException

logger = logging.getLogger(__name__)

class GitHubService:
    """Service for fetching content from Ethereum-related GitHub repositories"""

    def __init__(self):
        self.github_token = os.environ.get('GITHUB_TOKEN')
        if not self.github_token:
            logger.warning("GitHub token not found, using unauthenticated client")
            self.github = Github()
        else:
            logger.info("Initializing GitHub client with authentication")
            self.github = Github(self.github_token)

        # Core Ethereum repositories to monitor
        self.repositories = [
            "ethereum/pm",  # Core protocol meetings
            "ethereum/EIPs",  # Ethereum Improvement Proposals
            "ethereum/execution-apis",  # Execution layer API specs
            "ethereum/execution-specs",  # Execution layer specs
            "ethereum/consensus-specs"  # Consensus layer specs
        ]

        self.max_retries = 3
        self.base_delay = 2  # Base delay for exponential backoff
        self.max_workers = 3  # Number of parallel workers for fetching

    def _handle_rate_limit(self):
        """Handle GitHub API rate limiting with exponential backoff"""
        rate_limit = self.github.get_rate_limit()
        reset_time = rate_limit.core.reset
        current_time = datetime.now(pytz.UTC)

        if reset_time > current_time:
            sleep_time = (reset_time - current_time).total_seconds() + 1
            logger.warning(f"Rate limit exceeded. Waiting {sleep_time:.1f} seconds for reset...")
            time.sleep(sleep_time)
            return True
        return False

    def _fetch_repository_content(self, repo_name: str, start_date: datetime, end_date: datetime):
        """Fetch both issues and commits from a repository within the date range"""
        content = []
        retry_count = 0

        while retry_count < self.max_retries:
            try:
                logger.info(f"Fetching content from {repo_name}")
                repo = self.github.get_repo(repo_name)

                # Fetch issues and pull requests
                issues = list(repo.get_issues(state='all', since=start_date))
                for issue in issues:
                    created_at = issue.created_at.replace(tzinfo=pytz.UTC)
                    if start_date <= created_at <= end_date:
                        content.append({
                            'type': 'issue',
                            'title': issue.title,
                            'url': issue.html_url,
                            'body': issue.body,
                            'created_at': created_at,
                            'repository': repo_name,
                            'labels': [label.name for label in issue.labels]
                        })

                # Fetch commits
                commits = list(repo.get_commits(since=start_date, until=end_date))
                for commit in commits:
                    # Skip merge commits
                    if len(commit.parents) > 1:
                        continue

                    commit_date = commit.commit.author.date.replace(tzinfo=pytz.UTC)
                    if start_date <= commit_date <= end_date:
                        # Get first line of commit message as title
                        message_lines = commit.commit.message.split('\n')
                        title = message_lines[0]
                        content.append({
                            'type': 'commit',
                            'title': title,
                            'url': commit.html_url,
                            'body': commit.commit.message,
                            'created_at': commit_date,
                            'repository': repo_name,
                            'author': commit.commit.author.name
                        })

                logger.info(f"Successfully fetched {len(content)} items from {repo_name}")
                return content

            except RateLimitExceededException:
                if self._handle_rate_limit():
                    retry_count += 1
                    continue
                else:
                    logger.error(f"Rate limit handling failed for {repo_name}")
                    return []

            except GithubException as e:
                logger.error(f"GitHub API error for {repo_name}: {str(e)}")
                retry_count += 1
                delay = self.base_delay * (2 ** retry_count)
                time.sleep(delay)
                continue

            except Exception as e:
                logger.error(f"Unexpected error fetching from {repo_name}: {str(e)}")
                return []

        logger.error(f"Failed to fetch from {repo_name} after {self.max_retries} retries")
        return []

    def fetch_recent_content(self, start_date=None, end_date=None):
        """
        Fetch content from all monitored Ethereum repositories in parallel.

        Args:
            start_date: Start date for content fetching (default: 7 days ago)
            end_date: End date for content fetching (default: now)

        Returns:
            List of dictionaries containing fetched content
        """
        if start_date is None:
            # Default to last 7 days
            end_date = datetime.now(pytz.UTC)
            start_date = end_date - timedelta(days=7)

        if not isinstance(start_date, datetime):
            start_date = datetime.fromisoformat(str(start_date))
        if not isinstance(end_date, datetime):
            end_date = datetime.fromisoformat(str(end_date))

        # Ensure dates are timezone-aware
        if start_date.tzinfo is None:
            start_date = pytz.UTC.localize(start_date)
        if end_date.tzinfo is None:
            end_date = pytz.UTC.localize(end_date)

        logger.info(f"Fetching content from {start_date} to {end_date}")

        all_content = []
        repo_stats = {}

        # Use ThreadPoolExecutor for parallel fetching
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_repo = {
                executor.submit(self._fetch_repository_content, repo, start_date, end_date): repo 
                for repo in self.repositories
            }

            for future in as_completed(future_to_repo):
                repo = future_to_repo[future]
                try:
                    content = future.result()
                    if content:
                        all_content.extend(content)
                        repo_stats[repo] = len(content)
                        logger.info(f"Added {len(content)} items from {repo}")
                    else:
                        logger.warning(f"No content fetched from {repo}")
                        repo_stats[repo] = 0
                except Exception as e:
                    logger.error(f"Error processing content from {repo}: {str(e)}")
                    repo_stats[repo] = 0

        # Log repository statistics
        logger.info("Content fetch complete. Repository statistics:")
        for repo, count in repo_stats.items():
            logger.info(f"- {repo}: {count} items")

        # Sort content by date
        all_content.sort(key=lambda x: x['created_at'], reverse=True)

        return all_content