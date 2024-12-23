import os
import logging
from datetime import datetime, timedelta
from github import Github
from github.GithubException import GithubException

logger = logging.getLogger(__name__)

class GitHubService:
    def __init__(self):
        self.github = Github()
        self.pm_repo = "ethereum/pm"

    def fetch_recent_content(self):
        """Fetch content from Ethereum PM repository from the past week"""
        try:
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

            return content

        except GithubException as e:
            logger.error(f"GitHub API error: {str(e)}")
            return []
        except Exception as e:
            logger.error(f"Error fetching GitHub content: {str(e)}")
            return []
