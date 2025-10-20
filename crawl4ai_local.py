class AsyncWebCrawler:
    async def cleanup(self):
        """Force cleanup of browser resources."""
        try:
            if hasattr(self, 'browser') and self.browser:
                contexts = self.browser.contexts
                for context in contexts:
                    for page in context.pages:
                        await page.close()
                    await context.clear_cookies()
                    await context.clear_permissions()
                    await context.clear_cache()
                await self.browser.close()
            gc.collect()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")