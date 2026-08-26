"""App list definition for the Composio App Research Pipeline.

Defines the complete list of 100 apps (10 per category) across 10 categories
that the pipeline will research. Includes the AppInput dataclass and the
CATEGORIES constant.
"""

from dataclasses import dataclass

from composio_research.config import CATEGORIES


@dataclass
class AppInput:
    """Input specification for a single app to be researched.

    Attributes:
        app_name: Display name of the application.
        category: Category the app belongs to; must be one of CATEGORIES.
    """

    app_name: str
    category: str

    def __post_init__(self) -> None:
        if self.category not in CATEGORIES:
            raise ValueError(
                f"Invalid category '{self.category}'. Must be one of: {CATEGORIES}"
            )


APP_LIST: list[AppInput] = [
    # CRM & Sales (10)
    AppInput("Salesforce", "CRM & Sales"),
    AppInput("HubSpot CRM", "CRM & Sales"),
    AppInput("Pipedrive", "CRM & Sales"),
    AppInput("Zoho CRM", "CRM & Sales"),
    AppInput("Freshsales", "CRM & Sales"),
    AppInput("Close", "CRM & Sales"),
    AppInput("Copper", "CRM & Sales"),
    AppInput("Monday Sales CRM", "CRM & Sales"),
    AppInput("Insightly", "CRM & Sales"),
    AppInput("Nutshell", "CRM & Sales"),
    # Support & Helpdesk (10)
    AppInput("Zendesk", "Support & Helpdesk"),
    AppInput("Freshdesk", "Support & Helpdesk"),
    AppInput("Intercom", "Support & Helpdesk"),
    AppInput("Help Scout", "Support & Helpdesk"),
    AppInput("Jira Service Management", "Support & Helpdesk"),
    AppInput("ServiceNow", "Support & Helpdesk"),
    AppInput("Kayako", "Support & Helpdesk"),
    AppInput("Zoho Desk", "Support & Helpdesk"),
    AppInput("Front", "Support & Helpdesk"),
    AppInput("LiveAgent", "Support & Helpdesk"),
    # Communications & Messaging (10)
    AppInput("Slack", "Communications & Messaging"),
    AppInput("Microsoft Teams", "Communications & Messaging"),
    AppInput("Discord", "Communications & Messaging"),
    AppInput("Twilio", "Communications & Messaging"),
    AppInput("Zoom", "Communications & Messaging"),
    AppInput("Telegram", "Communications & Messaging"),
    AppInput("WhatsApp Business", "Communications & Messaging"),
    AppInput("SendGrid", "Communications & Messaging"),
    AppInput("Vonage", "Communications & Messaging"),
    AppInput("RingCentral", "Communications & Messaging"),
    # Marketing/Ads/Email/Social (10)
    AppInput("Mailchimp", "Marketing/Ads/Email/Social"),
    AppInput("HubSpot Marketing", "Marketing/Ads/Email/Social"),
    AppInput("Google Ads", "Marketing/Ads/Email/Social"),
    AppInput("Facebook Ads", "Marketing/Ads/Email/Social"),
    AppInput("Hootsuite", "Marketing/Ads/Email/Social"),
    AppInput("Buffer", "Marketing/Ads/Email/Social"),
    AppInput("ActiveCampaign", "Marketing/Ads/Email/Social"),
    AppInput("Constant Contact", "Marketing/Ads/Email/Social"),
    AppInput("Brevo", "Marketing/Ads/Email/Social"),
    AppInput("Klaviyo", "Marketing/Ads/Email/Social"),
    # Ecommerce (10)
    AppInput("Shopify", "Ecommerce"),
    AppInput("WooCommerce", "Ecommerce"),
    AppInput("BigCommerce", "Ecommerce"),
    AppInput("Magento", "Ecommerce"),
    AppInput("Stripe", "Ecommerce"),
    AppInput("Square", "Ecommerce"),
    AppInput("PayPal", "Ecommerce"),
    AppInput("Amazon Seller", "Ecommerce"),
    AppInput("Etsy", "Ecommerce"),
    AppInput("Wix eCommerce", "Ecommerce"),
    # Data/SEO/Scraping (10)
    AppInput("Ahrefs", "Data/SEO/Scraping"),
    AppInput("SEMrush", "Data/SEO/Scraping"),
    AppInput("Moz", "Data/SEO/Scraping"),
    AppInput("ScrapingBee", "Data/SEO/Scraping"),
    AppInput("Apify", "Data/SEO/Scraping"),
    AppInput("Clearbit", "Data/SEO/Scraping"),
    AppInput("ZoomInfo", "Data/SEO/Scraping"),
    AppInput("SimilarWeb", "Data/SEO/Scraping"),
    AppInput("Google Analytics", "Data/SEO/Scraping"),
    AppInput("Mixpanel", "Data/SEO/Scraping"),
    # Developer/Infra/Data (10)
    AppInput("GitHub", "Developer/Infra/Data"),
    AppInput("GitLab", "Developer/Infra/Data"),
    AppInput("AWS", "Developer/Infra/Data"),
    AppInput("Vercel", "Developer/Infra/Data"),
    AppInput("Docker Hub", "Developer/Infra/Data"),
    AppInput("Datadog", "Developer/Infra/Data"),
    AppInput("PagerDuty", "Developer/Infra/Data"),
    AppInput("Sentry", "Developer/Infra/Data"),
    AppInput("Terraform Cloud", "Developer/Infra/Data"),
    AppInput("CircleCI", "Developer/Infra/Data"),
    # Productivity & PM (10)
    AppInput("Notion", "Productivity & PM"),
    AppInput("Asana", "Productivity & PM"),
    AppInput("Trello", "Productivity & PM"),
    AppInput("Monday.com", "Productivity & PM"),
    AppInput("ClickUp", "Productivity & PM"),
    AppInput("Jira", "Productivity & PM"),
    AppInput("Linear", "Productivity & PM"),
    AppInput("Todoist", "Productivity & PM"),
    AppInput("Airtable", "Productivity & PM"),
    AppInput("Basecamp", "Productivity & PM"),
    # Finance & Fintech (10)
    AppInput("Stripe Billing", "Finance & Fintech"),
    AppInput("QuickBooks", "Finance & Fintech"),
    AppInput("Xero", "Finance & Fintech"),
    AppInput("Plaid", "Finance & Fintech"),
    AppInput("Wise", "Finance & Fintech"),
    AppInput("Brex", "Finance & Fintech"),
    AppInput("Wave", "Finance & Fintech"),
    AppInput("FreshBooks", "Finance & Fintech"),
    AppInput("Gusto", "Finance & Fintech"),
    AppInput("Mercury", "Finance & Fintech"),
    # AI/Research/Media (10)
    AppInput("OpenAI", "AI/Research/Media"),
    AppInput("Anthropic", "AI/Research/Media"),
    AppInput("Cohere", "AI/Research/Media"),
    AppInput("Stability AI", "AI/Research/Media"),
    AppInput("ElevenLabs", "AI/Research/Media"),
    AppInput("Midjourney", "AI/Research/Media"),
    AppInput("Perplexity", "AI/Research/Media"),
    AppInput("AssemblyAI", "AI/Research/Media"),
    AppInput("Deepgram", "AI/Research/Media"),
    AppInput("Replicate", "AI/Research/Media"),
]
