import type { Data, Route } from '@/types';
import parser from '@/utils/rss-parser';

export const route: Route = {
    path: '/news',
    categories: ['traditional-media'],
    example: '/voa/news',
    features: {
        requireConfig: false, requirePuppeteer: false, antiCrawler: false,
        supportBT: false, supportPodcast: false, supportScihub: false,
    },
    name: 'News',
    maintainers: ['8cli'],
    handler,
    url: 'https://www.voanews.com/rss/',
};

async function handler(): Promise<Data> {
    const feed = await parser.parseURL('https://www.voanews.com/rss/');
    return {
        title: feed.title ?? 'VOA',
        link: feed.link ?? 'https://www.voanews.com/rss/',
        item: feed.items.map((i) => ({
            title: i.title,
            link: i.link,
            pubDate: i.pubDate,
            author: i.creator,
        })),
    };
}
