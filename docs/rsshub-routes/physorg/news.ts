import type { Data, Route } from '@/types';
import parser from '@/utils/rss-parser';

export const route: Route = {
    path: '/news',
    categories: ['traditional-media'],
    example: '/physorg/news',
    features: {
        requireConfig: false, requirePuppeteer: false, antiCrawler: false,
        supportBT: false, supportPodcast: false, supportScihub: false,
    },
    name: 'News',
    maintainers: ['8cli'],
    handler,
    url: 'https://phys.org/rss-feed/',
};

async function handler(): Promise<Data> {
    const feed = await parser.parseURL('https://phys.org/rss-feed/');
    return {
        title: feed.title ?? 'Phys.org',
        link: feed.link ?? 'https://phys.org/rss-feed/',
        item: feed.items.map((i) => ({
            title: i.title,
            link: i.link,
            pubDate: i.pubDate,
            author: i.creator,
        })),
    };
}
