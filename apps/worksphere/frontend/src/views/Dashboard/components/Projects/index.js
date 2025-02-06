import { Card, Typography, Box, LinearProgress } from '@mui/material';

const projects = [
  {
    img: '/static/images/home-decor-1.jpg',
    title: 'Modern',
    description: 'As Uber works through a huge amount of internal management turmoil.',
    members: [
      { img: '/static/images/team-1.jpg', name: 'Ryan Tompson' },
      { img: '/static/images/team-2.jpg', name: 'Romina Hadid' },
      { img: '/static/images/team-3.jpg', name: 'Alexander Smith' },
      { img: '/static/images/team-4.jpg', name: 'Jessica Doe' },
    ],
    budget: '$14,000',
    completion: 60,
  },
  {
    img: '/static/images/home-decor-2.jpg',
    title: 'Scandinavian',
    description: 'Music is something that every person has their own specific opinion about.',
    members: [
      { img: '/static/images/team-3.jpg', name: 'Nick Daniel' },
      { img: '/static/images/team-4.jpg', name: 'Peterson' },
      { img: '/static/images/team-1.jpg', name: 'Elena Morison' },
    ],
    budget: '$1,800',
    completion: 90,
  },
  {
    img: '/static/images/home-decor-3.jpg',
    title: 'Minimalist',
    description: 'Different people have different taste, and various types of music.',
    members: [
      { img: '/static/images/team-2.jpg', name: 'Peterson' },
      { img: '/static/images/team-4.jpg', name: 'Nick Daniel' },
      { img: '/static/images/team-1.jpg', name: 'Ryan Tompson' },
      { img: '/static/images/team-3.jpg', name: 'Alexander Smith' },
    ],
    budget: '$9,000',
    completion: 40,
  },
];

function Projects() {
  return (
    <Card>
      <Box p={3}>
        <Box mb={3} display="flex" justifyContent="space-between" alignItems="center">
          <Box>
            <Typography variant="h6" color="text.primary" gutterBottom>
              Projects
            </Typography>
            <Typography variant="body2" color="text.secondary">
              <Typography component="span" variant="body2" color="text.primary" fontWeight="bold">
                30 done
              </Typography>{' '}
              this month
            </Typography>
          </Box>
        </Box>

        {projects.map((project, index) => (
          <Box
            key={project.title}
            display="flex"
            alignItems="center"
            mb={index === projects.length - 1 ? 0 : 3}
          >
            {/* Project Image */}
            <Box
              component="img"
              src={project.img}
              alt={project.title}
              sx={{
                width: 48,
                height: 48,
                borderRadius: 1,
                objectFit: 'cover',
                mr: 2,
              }}
            />

            {/* Project Info */}
            <Box flexGrow={1}>
              <Typography variant="subtitle2" fontWeight="bold" gutterBottom>
                {project.title}
              </Typography>
              <Typography variant="body2" color="text.secondary" noWrap>
                {project.description}
              </Typography>
            </Box>

            {/* Project Details */}
            <Box
              ml={2}
              display="flex"
              flexDirection="column"
              alignItems="flex-end"
              minWidth={120}
            >
              <Typography variant="caption" color="text.secondary" mb={1}>
                {project.budget}
              </Typography>
              <Box width="100%">
                <LinearProgress
                  variant="determinate"
                  value={project.completion}
                  sx={{
                    height: 6,
                    borderRadius: 3,
                    backgroundColor: 'grey.200',
                    '& .MuiLinearProgress-bar': {
                      borderRadius: 3,
                      backgroundColor: project.completion >= 90
                        ? 'success.main'
                        : project.completion >= 60
                          ? 'info.main'
                          : 'warning.main',
                    },
                  }}
                />
              </Box>
            </Box>
          </Box>
        ))}
      </Box>
    </Card>
  );
}

export default Projects; 