import type { Data, Route } from '@/types';
import parser from '@/utils/rss-parser';

export const route: Route = {
    path: '/news',
    categories: ['traditional-media'],
    example: '/newyorktimes/news',
    features: {
        requireConfig: false, requirePuppeteer: false, antiCrawler: false,
        supportBT: false, supportPodcast: false, supportScihub: false,
    },
    name: 'News',
    maintainers: ['8cli'],
    handler,
    url: 'https://rss.nytimes.com/services/xml/rss/nyt/World.xml',
};

async function handler(): Promise<Data> {
    const feed = await parser.parseURL('https://rss.nytimes.com/services/xml/rss/nyt/World.xml');
    return {
        title: feed.title ?? 'New York Times',
        link: feed.link ?? 'https://rss.nytimes.com/services/xml/rss/nyt/World.xml',
        item: feed.items.map((i) => ({
            title: i.title,
            link: i.link,
            pubDate: i.pubDate,
            author: i.creator,
        })),
    };
}
