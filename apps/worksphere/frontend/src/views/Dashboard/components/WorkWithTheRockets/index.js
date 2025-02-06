import { Card, Icon, Typography, Box } from '@mui/material';

function WorkWithTheRockets() {
  return (
    <Card sx={{ height: '100%' }}>
      <Box position="relative" height="100%" p={2}>
        <Box
          display="flex"
          flexDirection="column"
          height="100%"
          py={2}
          px={2}
          borderRadius={2}
          sx={{
            backgroundImage: (theme) => `linear-gradient(310deg, 
              ${theme.palette.gradients?.dark?.main || 'rgba(20, 23, 39, 0.8)'}, 
              ${theme.palette.gradients?.dark?.state || 'rgba(58, 65, 111, 0.8)'}), 
              url(/static/images/ivancik.jpg)`,
            backgroundSize: 'cover',
          }}
        >
          <Box mb={3} pt={1}>
            <Typography variant="h5" color="white" fontWeight="bold">
              Work with the rockets
            </Typography>
          </Box>
          <Box mb={2}>
            <Typography variant="body2" color="white">
              Wealth creation is an evolutionarily recent positive-sum game. It is all about who take the opportunity first.
            </Typography>
          </Box>
          <Box
            component="a"
            href="#"
            sx={{
              mt: 'auto',
              mr: 'auto',
              display: 'inline-flex',
              alignItems: 'center',
              cursor: 'pointer',
              color: 'white',
              typography: 'button',
              fontWeight: 'medium',
              textDecoration: 'none',
              '& .MuiIcon-root': {
                fontSize: '1.125rem',
                transform: 'translate(2px, -0.5px)',
                transition: 'transform 0.2s cubic-bezier(0.34,1.61,0.7,1.3)',
              },
              '&:hover .MuiIcon-root': {
                transform: 'translate(6px, -0.5px)',
              },
            }}
          >
            Read More
            <Icon sx={{ fontWeight: 'bold' }}>arrow_forward</Icon>
          </Box>
        </Box>
      </Box>
    </Card>
  );
}

export default WorkWithTheRockets; 