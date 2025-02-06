import { Card, Icon, Typography, Box } from '@mui/material';
import Timeline from '@mui/lab/Timeline';
import TimelineItem from '@mui/lab/TimelineItem';
import TimelineSeparator from '@mui/lab/TimelineSeparator';
import TimelineConnector from '@mui/lab/TimelineConnector';
import TimelineContent from '@mui/lab/TimelineContent';
import TimelineDot from '@mui/lab/TimelineDot';

const timelineItems = [
  {
    color: 'success',
    icon: 'notifications',
    title: '$2400, Design changes',
    time: '22 DEC 7:20 PM',
  },
  {
    color: 'error',
    icon: 'inventory_2',
    title: 'New order #1832412',
    time: '21 DEC 11:21 PM',
  },
  {
    color: 'info',
    icon: 'shopping_cart',
    title: 'Server payments for April',
    time: '21 DEC 9:28 PM',
  },
  {
    color: 'warning',
    icon: 'payment',
    title: 'New card added for order #4395133',
    time: '20 DEC 2:20 AM',
  },
  {
    color: 'primary',
    icon: 'vpn_key',
    title: 'New card added for order #4395133',
    time: '18 DEC 4:54 AM',
  },
];

function OrderOverview() {
  return (
    <Card>
      <Box p={3}>
        <Box mb={3}>
          <Typography variant="h6" color="text.primary">
            Orders overview
          </Typography>
          <Box display="flex" alignItems="center" mt={0.5}>
            <Box
              component="span"
              display="flex"
              alignItems="center"
              color="success.main"
            >
              <Icon sx={{ fontSize: '1rem', mr: 0.25 }}>arrow_upward</Icon>
              <Typography variant="button" fontWeight="bold">
                24%
              </Typography>
            </Box>
            <Typography variant="button" color="text.secondary" ml={0.5}>
              this month
            </Typography>
          </Box>
        </Box>

        <Timeline
          sx={{
            [`& .MuiTimelineItem-root:before`]: {
              display: 'none',
            },
            p: 0,
            m: 0,
          }}
        >
          {timelineItems.map((item, index) => (
            <TimelineItem key={item.title}>
              <TimelineSeparator>
                <TimelineDot
                  sx={{
                    backgroundColor: item.color + '.main',
                    p: 1,
                    minWidth: 'auto',
                  }}
                >
                  <Icon sx={{ color: 'white', fontSize: '1rem' }}>
                    {item.icon}
                  </Icon>
                </TimelineDot>
                {index < timelineItems.length - 1 && (
                  <TimelineConnector />
                )}
              </TimelineSeparator>
              <TimelineContent sx={{ pt: 0, pb: 2 }}>
                <Typography variant="subtitle2" fontWeight="bold">
                  {item.title}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {item.time}
                </Typography>
              </TimelineContent>
            </TimelineItem>
          ))}
        </Timeline>
      </Box>
    </Card>
  );
}

export default OrderOverview; 