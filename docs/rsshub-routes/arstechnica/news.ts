import type { Data, Route } from '@/types';
import parser from '@/utils/rss-parser';

export const route: Route = {
    path: '/news',
    categories: ['traditional-media'],
    example: '/arstechnica/news',
    features: {
        requireConfig: false, requirePuppeteer: false, antiCrawler: false,
        supportBT: false, supportPodcast: false, supportScihub: false,
    },
    name: 'News',
    maintainers: ['8cli'],
    handler,
    url: 'https://feeds.arstechnica.com/arstechnica/technology-lab',
};

async function handler(): Promise<Data> {
    const feed = await parser.parseURL('https://feeds.arstechnica.com/arstechnica/technology-lab');
    return {
        title: feed.title ?? 'Ars Technica',
        link: feed.link ?? 'https://feeds.arstechnica.com/arstechnica/technology-lab',
        item: feed.items.map((i) => ({
            title: i.title,
            link: i.link,
            pubDate: i.pubDate,
            author: i.creator,
        })),
    };
}
