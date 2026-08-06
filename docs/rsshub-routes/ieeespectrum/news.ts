import type { Data, Route } from '@/types';
import parser from '@/utils/rss-parser';

export const route: Route = {
    path: '/news',
    categories: ['traditional-media'],
    example: '/ieeespectrum/news',
    features: {
        requireConfig: false, requirePuppeteer: false, antiCrawler: false,
        supportBT: false, supportPodcast: false, supportScihub: false,
    },
    name: 'News',
    maintainers: ['8cli'],
    handler,
    url: 'https://spectrum.ieee.org/feed/rss',
};

async function handler(): Promise<Data> {
    const feed = await parser.parseURL('https://spectrum.ieee.org/feed/rss');
    return {
        title: feed.title ?? 'IEEE Spectrum',
        link: feed.link ?? 'https://spectrum.ieee.org/feed/rss',
        item: feed.items.map((i) => ({
            title: i.title,
            link: i.link,
            pubDate: i.pubDate,
            author: i.creator,
        })),
    };
}
