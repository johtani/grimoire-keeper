# Web UI User Guide

## Overview

Grimoire Keeper Web UI provides a browser-based interface for searching and managing your processed web content. The interface consists of two main screens: Search and Page Management.

## Accessing the Web UI

Once deployed, access the web interface at:
```
http://localhost:8001
```

## Search Interface

### Basic Search

1. **Enter Search Query**: Type your search terms in the main search box
2. **Select Vector Type**: Choose the search target:
   - **Content Vector**: Search within full article content (default)
   - **Title Vector**: Search within titles and summaries only
   - **Memo Vector**: Search within your personal memos only
3. **Click Search**: Execute the search

### Advanced Filtering

Use the filter options to narrow your search results:

#### Date Range Filter
- **From Date**: Start date for content creation
- **To Date**: End date for content creation
- Format: YYYY-MM-DD

#### URL Filter
- Filter results by URL substring
- Example: "github.com" to find only GitHub pages

#### Keywords Filter
- Filter by specific keywords present in the content
- Enter comma-separated keywords

### Search Results

Results display:
- **Title**: Article title with link to original URL
- **URL**: Source URL
- **Score**: Relevance score (0.0 to 1.0)
- **Summary**: AI-generated summary
- **Keywords**: Extracted keywords
- **Memo**: Your personal memo (if any)
- **Date**: When the content was processed

### Vector Type Differences

#### Content Vector
- Searches through all content chunks
- Best for finding specific information within articles
- Returns multiple results per page if relevant

#### Title Vector  
- Searches only in titles and summaries
- Best for finding articles by topic or theme
- Returns one result per page (avoids duplicates)
- Faster search with focused results

#### Memo Vector
- Searches only in your personal memos
- Best for finding content by your own notes
- Returns one result per page

## Page Management Interface

### Page List

View all processed pages with:
- **ID**: Unique page identifier
- **URL**: Source URL (clickable)
- **Title**: Extracted title
- **Status**: Processing status
- **Date**: Processing date
- **Actions**: View details, reprocess, delete

### Status Filtering

Filter pages by processing status:
- **All**: Show all pages (default)
- **Completed**: Successfully processed pages
- **Processing**: Currently being processed
- **Failed**: Failed processing attempts

### Page Details

Click on any page to view:
- Full content summary
- Complete keyword list
- Processing logs
- Vector storage status
- Raw content (if available)

## Tips for Effective Searching

### Query Optimization
- Use natural language queries for vector search
- Be specific about what you're looking for
- Try different vector types for different use cases

### Filter Combinations
- Combine date ranges with keyword filters for precise results
- Use URL filters to search within specific domains
- Leverage memo search to find content by your own categorization

### Vector Selection Strategy
- **Content Vector**: When looking for specific information or quotes
- **Title Vector**: When browsing by topic or finding overview content
- **Memo Vector**: When searching by your own notes and categorization

## Keyboard Shortcuts

- **Enter**: Execute search
- **Ctrl+K**: Focus search box
- **Esc**: Clear search results

## Browser Compatibility

Supported browsers:
- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## Troubleshooting

### Search Not Working
1. Check if the API service is running (port 8000)
2. Verify Weaviate is accessible
3. Check browser console for errors

### No Results Found
1. Try broader search terms
2. Check date range filters
3. Try different vector types
4. Verify content has been processed

### Page Management Issues
1. Refresh the page list
2. Check processing status
3. Verify database connectivity

## Performance Notes

- Search results are limited to prevent slow responses
- Large result sets may take longer to load
- Vector searches are generally faster than keyword searches
- Title/memo vector searches are faster than content vector searches

## Privacy and Data

- All searches are performed locally on your server
- No search queries are sent to external services
- Content remains on your infrastructure
- Web UI communicates only with your local API