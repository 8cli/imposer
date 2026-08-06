import type { Data, Route } from '@/types';
import parser from '@/utils/rss-parser';

export const route: Route = {
    path: '/news',
    categories: ['traditional-media'],
    example: '/nasaspaceflight/news',
    features: {
        requireConfig: false, requirePuppeteer: false, antiCrawler: false,
        supportBT: false, supportPodcast: false, supportScihub: false,
    },
    name: 'News',
    maintainers: ['8cli'],
    handler,
    url: 'https://www.nasaspaceflight.com/feed/',
};

async function handler(): Promise<Data> {
    const feed = await parser.parseURL('https://www.nasaspaceflight.com/feed/');
    return {
        title: feed.title ?? 'NASA Spaceflight',
        link: feed.link ?? 'https://www.nasaspaceflight.com/feed/',
        item: feed.items.map((i) => ({
            title: i.title,
            link: i.link,
            pubDate: i.pubDate,
            author: i.creator,
        })),
    };
}
