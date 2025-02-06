import PropTypes from 'prop-types';
import { Card, Icon, Typography, Box } from '@mui/material';

function StatCard({ title, count, percentage, icon }) {
  return (
    <Card sx={{ height: '100%' }}>
      <Box p={2} display="flex" justifyContent="space-between">
        <Box>
          <Typography
            variant="button"
            color="text.secondary"
            fontWeight="medium"
            textTransform="capitalize"
          >
            {title}
          </Typography>
          <Typography variant="h5" fontWeight="bold" mt={1} mb={1}>
            {count}
          </Typography>
          <Box display="flex" alignItems="center">
            <Box
              component="span"
              display="flex"
              alignItems="center"
              color={percentage.color + '.main'}
              mr={0.5}
            >
              <Icon sx={{ fontSize: '1rem', mr: 0.25 }}>
                {percentage.text.includes('+') ? 'arrow_upward' : 'arrow_downward'}
              </Icon>
              <Typography variant="button" fontWeight="bold">
                {percentage.text}
              </Typography>
            </Box>
          </Box>
        </Box>
        <Box
          display="flex"
          alignItems="center"
          justifyContent="center"
          sx={{
            width: 48,
            height: 48,
            borderRadius: 1.5,
            backgroundColor: icon.color + '.lighter',
            color: icon.color + '.main',
          }}
        >
          <Icon>{icon.name}</Icon>
        </Box>
      </Box>
    </Card>
  );
}

StatCard.propTypes = {
  title: PropTypes.string.isRequired,
  count: PropTypes.string.isRequired,
  percentage: PropTypes.shape({
    color: PropTypes.oneOf(['success', 'error', 'warning', 'info']).isRequired,
    text: PropTypes.string.isRequired,
  }).isRequired,
  icon: PropTypes.shape({
    color: PropTypes.oneOf(['primary', 'secondary', 'info', 'success', 'warning', 'error']).isRequired,
    name: PropTypes.string.isRequired,
  }).isRequired,
};

export default StatCard; 