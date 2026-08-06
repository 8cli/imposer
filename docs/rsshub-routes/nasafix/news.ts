import type { Data, Route } from '@/types';
import got from '@/utils/got';
import parser from '@/utils/rss-parser';

export const route: Route = {
    path: '/news',
    categories: ['traditional-media'],
    example: '/nasafix/news',
    features: {
        requireConfig: false, requirePuppeteer: false, antiCrawler: false,
        supportBT: false, supportPodcast: false, supportScihub: false,
    },
    name: 'News',
    maintainers: ['8cli'],
    handler,
    url: 'https://www.nasa.gov/rss/dyn/breaking_news.rss',
};

async function handler(): Promise<Data> {
    const res = await got({
        url: 'https://www.nasa.gov/rss/dyn/breaking_news.rss',
        headers: { 'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36' },
        responseType: 'text',
    });
    const feed = await parser.parseString(res.data as string);
    return {
        title: feed.title ?? 'NASA',
        link: feed.link ?? 'https://www.nasa.gov/rss/dyn/breaking_news.rss',
        item: feed.items.map((i) => ({
            title: i.title,
            link: i.link,
            pubDate: i.pubDate,
            author: i.creator,
        })),
    };
}
