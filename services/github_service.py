import os
import logging
from datetime import datetime, timedelta
from github import Github
from github.GithubException import GithubException

logger = logging.getLogger(__name__)

class GitHubService:
    def __init__(self):
        github_token = os.environ.get('GITHUB_TOKEN')
        if not github_token:
            logger.warning("GitHub token not found, using unauthenticated client")
            self.github = Github()
        else:
            logger.info("Initializing GitHub client with authentication")
            self.github = Github(github_token)
        self.pm_repo = "ethereum/pm"

    def fetch_recent_content(self):
        """Fetch content from Ethereum PM repository from the past week"""
        try:
            logger.info(f"Fetching recent content from {self.pm_repo}")
            repo = self.github.get_repo(self.pm_repo)
            one_week_ago = datetime.utcnow() - timedelta(days=7)

            # Get recent issues and pull requests
            issues = repo.get_issues(state='all', since=one_week_ago)
            content = []

            for issue in issues:
                content.append({
                    'type': 'issue',
                    'title': issue.title,
                    'url': issue.html_url,
                    'body': issue.body,
                    'created_at': issue.created_at
                })
                logger.debug(f"Fetched issue: {issue.title}")

            # Get recent commits
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

            logger.info(f"Successfully fetched {len(content)} items from GitHub")
            return content

        except GithubException as e:
            logger.error(f"GitHub API error: {str(e)}")
            if e.status == 304:
                logger.error("Received 304 error - likely a rate limit or caching issue")
            elif e.status == 401:
                logger.error("Authentication failed - check GitHub token")
            elif e.status == 403:
                logger.error("Rate limit exceeded or permission denied")
            return []
        except Exception as e:
            logger.error(f"Error fetching GitHub content: {str(e)}")
            return []