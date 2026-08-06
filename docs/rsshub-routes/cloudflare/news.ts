import type { Data, Route } from '@/types';
import parser from '@/utils/rss-parser';

export const route: Route = {
    path: '/news',
    categories: ['traditional-media'],
    example: '/cloudflare/news',
    features: {
        requireConfig: false, requirePuppeteer: false, antiCrawler: false,
        supportBT: false, supportPodcast: false, supportScihub: false,
    },
    name: 'News',
    maintainers: ['8cli'],
    handler,
    url: 'https://blog.cloudflare.com/rss/',
};

async function handler(): Promise<Data> {
    const feed = await parser.parseURL('https://blog.cloudflare.com/rss/');
    return {
        title: feed.title ?? 'Cloudflare',
        link: feed.link ?? 'https://blog.cloudflare.com/rss/',
        item: feed.items.map((i) => ({
            title: i.title,
            link: i.link,
            pubDate: i.pubDate,
            author: i.creator,
        })),
    };
}
