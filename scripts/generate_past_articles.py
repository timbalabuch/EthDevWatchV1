def wait_for_generating_articles():
    """Wait until there are no articles in generating status."""
    while True:
        with app.app_context():
            generating = Article.query.filter_by(status='generating').count()
            if generating == 0:
                return
            logger.info(f"Waiting for {generating} article(s) to finish generating...")
            time.sleep(5)  # Wait for 5 seconds before checking again

def generate_past_articles(num_articles=10):
    """Generate specified number of past articles"""
    try:
        logger.info(f"=== Starting Generation of {num_articles} Past Articles ===")

        # Calculate current Monday
        current_date = datetime.utcnow()
        current_monday = current_date - timedelta(days=current_date.weekday())
        current_monday = current_monday.replace(hour=0, minute=0, second=0, microsecond=0)

        success_count = 0

        # Wait for any currently generating articles to complete before starting
        wait_for_generating_articles()

        # Generate articles for past weeks
        for i in range(1, num_articles + 1):
            target_date = current_monday - timedelta(weeks=i)
            logger.info(f"Generating article for week of {target_date.strftime('%Y-%m-%d')}")

            # Check for existing article before generating
            with app.app_context():
                existing = Article.query.filter(
                    Article.publication_date >= target_date,
                    Article.publication_date < target_date + timedelta(days=7)
                ).first()

                if existing:
                    logger.info(f"Article already exists for week of {target_date.strftime('%Y-%m-%d')}")
                    continue

            if generate_article_for_date(target_date):
                success_count += 1
                logger.info(f"Successfully generated article {success_count} of {num_articles}")

                # Wait for the current article to finish before starting the next one
                wait_for_generating_articles()
            else:
                logger.warning(f"Failed to generate article for week of {target_date.strftime('%Y-%m-%d')}")

        logger.info(f"=== Completed Generation of Past Articles ===")
        logger.info(f"Successfully generated {success_count} out of {num_articles} articles")
        return success_count

    except Exception as e:
        logger.error(f"Fatal error generating past articles: {str(e)}")
        return 0

if __name__ == "__main__":
    success_count = generate_past_articles()
    exit_code = 0 if success_count > 0 else 1
    sys.exit(exit_code)
