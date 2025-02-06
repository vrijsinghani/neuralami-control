import { Card, Icon, Grid, Typography, Box } from '@mui/material';

function BuildByDevelopers() {
  return (
    <Card>
      <Box p={2}>
        <Grid container spacing={3}>
          <Grid item xs={12} lg={6}>
            <Box display="flex" flexDirection="column" height="100%">
              <Box pt={1} mb={0.5}>
                <Typography variant="body2" color="text.secondary" fontWeight="medium">
                  Build by developers
                </Typography>
              </Box>
              <Typography variant="h5" fontWeight="bold" gutterBottom>
                Soft UI Dashboard
              </Typography>
              <Box mb={6}>
                <Typography variant="body2" color="text.secondary">
                  From colors, cards, typography to complex elements, you will find the full documentation.
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
                  color: 'text.secondary',
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
          </Grid>
          <Grid item xs={12} lg={5} sx={{ position: 'relative', ml: 'auto' }}>
            <Box
              height="100%"
              display="grid"
              justifyContent="center"
              alignItems="center"
              bgcolor="info.main"
              borderRadius={2}
              sx={{
                background: (theme) => `linear-gradient(310deg, ${theme.palette.info.main}, ${theme.palette.info.dark})`,
              }}
            >
              <Box
                component="img"
                src="/static/images/shapes/waves-white.svg"
                alt="waves"
                sx={{
                  display: 'block',
                  position: 'absolute',
                  left: 0,
                  width: '100%',
                  height: '100%',
                }}
              />
              <Box
                component="img"
                src="/static/images/illustrations/rocket-white.png"
                alt="rocket"
                width="100%"
                pt={3}
              />
            </Box>
          </Grid>
        </Grid>
      </Box>
    </Card>
  );
}

export default BuildByDevelopers; 