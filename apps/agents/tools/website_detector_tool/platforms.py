{
  "platforms": [
    {
      "name": "WordPress",
      "checks": [
        {"html": "wp-content"},
        {"meta": {"name": "generator", "value": "wordpress"}},
        {"path": "/wp-admin/"}
      ]
    },
    {
      "name": "Drupal",
      "checks": [
        {"meta": {"name": "generator", "value": "drupal"}},
        {"html": "sites/default"},
        {"header": {"X-Generator": "Drupal"}}
      ]
    },
    {
      "name": "Joomla",
      "checks": [
        {"meta": {"name": "generator", "value": "joomla"}},
        {"html": "joomla"},
        {"path": "/administrator/"}
      ]
    },
    {
      "name": "TYPO3",
      "checks": [
        {"html": "typo3"},
        {"meta": {"name": "generator", "value": "typo3"}}
      ]
    },
    {
      "name": "Craft CMS",
      "checks": [
        {"html": "craftcms.com"},
        {"html": "craft", "additional": "cms"}
      ]
    },
    {
      "name": "ExpressionEngine",
      "checks": [
        {"html": "expressionengine"},
        {"cookie": "exp_"}
      ]
    },
    {
      "name": "Concrete CMS",
      "checks": [
        {"html": "concrete5"},
        {"meta": {"name": "generator", "value": "concrete5"}}
      ]
    },
    {
      "name": "Sitecore",
      "checks": [
        {"html": "sitecore"},
        {"cookie": "sc_"}
      ]
    },
    {
      "name": "Adobe Experience Manager",
      "checks": [
        {"html": "adobe"},
        {"html": "aem"},
        {"html": "cq_"}
      ]
    },
    {
      "name": "1C-Bitrix",
      "checks": [
        {"html": "bitrix"},
        {"cookie": "bx_"}
      ]
    },
    {
      "name": "Umbraco",
      "checks": [
        {"html": "umbraco"},
        {"cookie": "umb_"}
      ]
    },
    {
      "name": "MODX",
      "checks": [
        {"meta": {"name": "generator", "value": "modx"}},
        {"html": "modx"}
      ]
    },
    {
      "name": "SilverStripe",
      "checks": [
        {"html": "silverstripe"},
        {"meta": {"name": "generator", "value": "silverstripe"}}
      ]
    },
    {
      "name": "PyroCMS",
      "checks": [
        {"html": "pyrocms"},
        {"html": "powered by pyrocms"}
      ]
    },
    {
      "name": "Contao",
      "checks": [
        {"html": "contao"},
        {"meta": {"name": "generator", "value": "contao"}}
      ]
    },
    {
      "name": "Grav",
      "checks": [
        {"html": "grav"},
        {"meta": {"name": "generator", "value": "grav"}}
      ]
    },
    {
      "name": "October CMS",
      "checks": [
        {"html": "octobercms"},
        {"cookie": "october_session"}
      ]
    },
    {
      "name": "Shopify",
      "checks": [
        {"domain": ".myshopify.com"},
        {"html": "shopify"}
      ]
    },
    {
      "name": "Magento",
      "checks": [
        {"html": "mage"},
        {"html": "magento"},
        {"header": {"X-Magento-Cache-Control": null}}
      ]
    },
    {
      "name": "WooCommerce",
      "checks": [
        {"html": "woocommerce"},
        {"html": "wp-content/plugins/woocommerce"}
      ]
    },
    {
      "name": "BigCommerce",
      "checks": [
        {"html": "bigcommerce.com"},
        {"domain": "bigcommerce"}
      ]
    },
    {
      "name": "PrestaShop",
      "checks": [
        {"html": "prestashop"},
        {"cookie": "ps_"}
      ]
    },
    {
      "name": "OpenCart",
      "checks": [
        {"html": "opencart"},
        {"html": "catalog", "additional": "cart"}
      ]
    },
    {
      "name": "Volusion",
      "checks": [
        {"html": "volusion.com"},
        {"html": "v/vspfiles"}
      ]
    },
    {
      "name": "Shift4Shop",
      "checks": [
        {"html": "3dcart.com"},
        {"html": "shift4shop.com"}
      ]
    },
    {
      "name": "Zen Cart",
      "checks": [
        {"html": "zencart"},
        {"html": "zen-cart"}
      ]
    },
    {
      "name": "osCommerce",
      "checks": [
        {"html": "oscommerce"},
        {"html": "powered by oscommerce"}
      ]
    },
    {
      "name": "Sylius",
      "checks": [
        {"html": "sylius"},
        {"cookie": "sylius"}
      ]
    },
    {
      "name": "Spree Commerce",
      "checks": [
        {"html": "spree"},
        {"html": "powered by spree"}
      ]
    },
    {
      "name": "Wix",
      "checks": [
        {"html": "wix.com"},
        {"header": {"X-Wix": null}},
        {"html": "wixstatic.com"}
      ]
    },
    {
      "name": "Squarespace",
      "checks": [
        {"html": "squarespace"},
        {"header": {"X-ServedBy": "squarespace"}}
      ]
    },
    {
      "name": "GoDaddy Website Builder",
      "checks": [
        {"domain": "godaddysites.com"},
        {"html": "godaddy"}
      ]
    },
    {
      "name": "Weebly",
      "checks": [
        {"html": "weebly.com"},
        {"domain": "weebly"}
      ]
    },
    {
      "name": "Duda",
      "checks": [
        {"html": "duda.co"},
        {"html": "dmws"}
      ]
    },
    {
      "name": "Webflow",
      "checks": [
        {"html": "webflow.com"},
        {"domain": "webflow"}
      ]
    },
    {
      "name": "Jimdo",
      "checks": [
        {"html": "jimdo.com"},
        {"domain": "jimdosite.com"}
      ]
    },
    {
      "name": "Strikingly",
      "checks": [
        {"html": "strikingly.com"},
        {"domain": "strikingly.com"}
      ]
    },
    {
      "name": "Webnode",
      "checks": [
        {"html": "webnode.com"},
        {"domain": "webnode"}
      ]
    },
    {
      "name": "Voog",
      "checks": [
        {"html": "voog.com"},
        {"domain": "voog.com"}
      ]
    },
    {
      "name": "Blogger",
      "checks": [
        {"domain": "blogger.com"},
        {"domain": "blogspot.com"},
        {"html": "blogger"}
      ]
    },
    {
      "name": "Tumblr",
      "checks": [
        {"domain": "tumblr.com"},
        {"html": "tumblr"}
      ]
    },
    {
      "name": "Ghost",
      "checks": [
        {"meta": {"name": "generator", "value": "ghost"}},
        {"html": "ghost.org"}
      ]
    },
    {
      "name": "Medium",
      "checks": [
        {"domain": "medium.com"},
        {"html": "medium.com"}
      ]
    },
    {
      "name": "Laravel",
      "checks": [
        {"html": "laravel"},
        {"cookie": "laravel_session"},
        {"header": {"X-Powered-By": "PHP"}}
      ]
    },
    {
      "name": "Django",
      "checks": [
        {"html": "django"},
        {"cookie": "csrftoken"},
        {"header": {"X-Powered-By": "Python"}}
      ]
    },
    {
      "name": "Ruby on Rails",
      "checks": [
        {"html": "rails"},
        {"cookie": "rails"},
        {"header": {"X-Powered-By": "Ruby"}}
      ]
    },
    {
      "name": "CakePHP",
      "checks": [
        {"html": "cakephp"},
        {"cookie": "cake_"}
      ]
    },
    {
      "name": "Symfony",
      "checks": [
        {"html": "symfony"},
        {"cookie": "sf_"},
        {"header": {"X-Powered-By": "PHP"}}
      ]
    },
    {
      "name": "Flask",
      "checks": [
        {"html": "flask"},
        {"header": {"Server": "Werkzeug"}}
      ]
    },
    {
      "name": "Next.js",
      "checks": [
        {"html": "next.js"},
        {"header": {"Server": "Vercel"}}
      ]
    },
    {
      "name": "Express.js",
      "checks": [
        {"header": {"X-Powered-By": "Express"}}
      ]
    },
    {
      "name": "Nuxt.js",
      "checks": [
        {"html": "nuxt"},
        {"html": "__nuxt"}
      ]
    },
    {
      "name": "SvelteKit",
      "checks": [
        {"html": "sveltekit"},
        {"html": "svelte"}
      ]
    },
    {
      "name": "Angular",
      "checks": [
        {"html": "ng-version"},
        {"html": "angular"}
      ]
    },
    {
      "name": "Vue.js",
      "checks": [
        {"html": "vue"},
        {"html": "data-v-"}
      ]
    },
    {
      "name": "Spring",
      "checks": [
        {"html": "spring"},
        {"header": {"X-Powered-By": "Spring"}}
      ]
    },
    {
      "name": "CodeIgniter",
      "checks": [
        {"html": "codeigniter"},
        {"cookie": "ci_session"}
      ]
    },
    {
      "name": "Gatsby",
      "checks": [
        {"html": "gatsbyjs"},
        {"html": "gatsby"}
      ]
    },
    {
      "name": "Hugo",
      "checks": [
        {"meta": {"name": "generator", "value": "hugo"}}
      ]
    },
    {
      "name": "Jekyll",
      "checks": [
        {"meta": {"name": "generator", "value": "jekyll"}},
        {"html": "jekyll"}
      ]
    },
    {
      "name": "Hexo",
      "checks": [
        {"meta": {"name": "generator", "value": "hexo"}},
        {"html": "hexo"}
      ]
    },
    {
      "name": "Pelican",
      "checks": [
        {"meta": {"name": "generator", "value": "pelican"}},
        {"html": "pelican"}
      ]
    },
    {
      "name": "Eleventy",
      "checks": [
        {"html": "11ty"},
        {"html": "eleventy"}
      ]
    },
    {
      "name": "Astro",
      "checks": [
        {"html": "astro"},
        {"meta": {"name": "generator", "value": "astro"}}
      ]
    },
    {
      "name": "Docusaurus",
      "checks": [
        {"html": "docusaurus"},
        {"html": "powered by docusaurus"}
      ]
    },
    {
      "name": "MkDocs",
      "checks": [
        {"html": "mkdocs"},
        {"meta": {"name": "generator", "value": "mkdocs"}}
      ]
    },
    {
      "name": "Publii",
      "checks": [
        {"html": "publii"},
        {"meta": {"name": "generator", "value": "publii"}}
      ]
    },
    {
      "name": "HubSpot CMS",
      "checks": [
        {"html": "hubspot"},
        {"html": "hs-scripts.com"}
      ]
    },
    {
      "name": "Kentico",
      "checks": [
        {"html": "kentico"},
        {"cookie": "kentico"}
      ]
    },
    {
      "name": "Liferay",
      "checks": [
        {"html": "liferay"},
        {"cookie": "lfr_"}
      ]
    },
    {
      "name": "Contentful",
      "checks": [
        {"html": "contentful"},
        {"html": "powered by contentful"}
      ]
    },
    {
      "name": "Episerver",
      "checks": [
        {"html": "episerver"},
        {"cookie": "epi_"}
      ]
    },
    {
      "name": "Bloomreach",
      "checks": [
        {"html": "bloomreach"},
        {"html": "brxm"}
      ]
    },
    {
      "name": "Bubble",
      "checks": [
        {"html": "bubble"},
        {"domain": "bubbleapps.io"}
      ]
    },
    {
      "name": "Carrd",
      "checks": [
        {"html": "carrd"},
        {"domain": "carrd.co"}
      ]
    },
    {
      "name": "Framer",
      "checks": [
        {"html": "framer"},
        {"domain": "framer.app"}
      ]
    },
    {
      "name": "Notion Sites",
      "checks": [
        {"html": "notion.so"},
        {"html": "notion-site"}
      ]
    }
  ]
}