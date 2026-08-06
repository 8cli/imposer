import type { Data, Route } from '@/types';
import ofetch from '@/utils/ofetch';
import parser from '@/utils/rss-parser';

export const route: Route = {
    path: '/news',
    categories: ['technology'],
    example: '/iter/news',
    parameters: {},
    features: {
        requireConfig: false,
        requirePuppeteer: false,
        antiCrawler: false,
        supportBT: false,
        supportPodcast: false,
        supportScihub: false,
    },
    name: 'News',
    maintainers: ['8cli'],
    handler,
    url: 'https://www.iter.org/rss.xml',
};

async function handler(): Promise<Data> {
    // ITER 官方 RSS — 直接转发
    const rssUrl = 'https://www.iter.org/rss.xml';
    const xml = await ofetch(rssUrl, {
        headers: {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36',
            'Accept': 'application/rss+xml, application/xml, text/xml, */*',
        },
        parseResponse: (t: string) => t,
    });
    const feed = await parser.parseString(xml);
    return {
        title: feed.title ?? 'ITER News',
        link: feed.link ?? 'https://www.iter.org/',
        item: feed.items.map((i) => ({
            title: i.title,
            link: i.link,
            pubDate: i.pubDate,
            description: i.contentSnippet,
        })),
    };
}
