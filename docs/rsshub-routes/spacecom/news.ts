import type { Data, Route } from '@/types';
import parser from '@/utils/rss-parser';

export const route: Route = {
    path: '/news',
    categories: ['traditional-media'],
    example: '/spacecom/news',
    features: {
        requireConfig: false, requirePuppeteer: false, antiCrawler: false,
        supportBT: false, supportPodcast: false, supportScihub: false,
    },
    name: 'News',
    maintainers: ['8cli'],
    handler,
    url: 'https://www.space.com/feeds/all',
};

async function handler(): Promise<Data> {
    const feed = await parser.parseURL('https://www.space.com/feeds/all');
    return {
        title: feed.title ?? 'Space.com',
        link: feed.link ?? 'https://www.space.com/feeds/all',
        item: feed.items.map((i) => ({
            title: i.title,
            link: i.link,
            pubDate: i.pubDate,
            author: i.creator,
        })),
    };
}
